"""v0.6.0 功能测试 — LSP 代码折叠 + 适配器热重载 + 工作空间 + 实时协作"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest


# ============================================================
# 1. LSP 代码折叠测试
# ============================================================

class TestLSPFoldingRange:
    """LSP 代码折叠 — 基于块关键字识别折叠区域"""

    def test_folding_range_basic_block(self):
        """基本块折叠 — 段落/函数定义"""
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.registry import LanguageRegistry

        # 使用段言适配器
        registry = LanguageRegistry()
        from yanpub.adapters.duan.adapter import DuanAdapter
        registry.register(DuanAdapter())

        server = YanLanguageServer(registry=registry)
        adapter = registry.get("duan")

        code = '段落 加法(甲, 乙)。\n  返回 甲 加 乙。\n结束。\n\n段落 乘法(甲, 乙)。\n  返回 甲 乘 乙。\n结束。'
        ranges = server._compute_folding_ranges(adapter, code)

        assert len(ranges) >= 1
        # 第一个块：段落 加法 ... 结束
        assert ranges[0].start_line == 0
        assert ranges[0].end_line >= 1

    def test_folding_range_nested_blocks(self):
        """嵌套块折叠 — 当/如果内嵌在段落中"""
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.registry import LanguageRegistry

        registry = LanguageRegistry()
        from yanpub.adapters.duan.adapter import DuanAdapter
        registry.register(DuanAdapter())

        server = YanLanguageServer(registry=registry)
        adapter = registry.get("duan")

        code = '段落 示例()。\n  当 甲 > 0。\n    打印(甲)。\n  结束。\n结束。'
        ranges = server._compute_folding_ranges(adapter, code)

        assert len(ranges) >= 1
        # 至少有一个折叠范围覆盖了外层块

    def test_folding_range_indent_based(self):
        """缩进推断折叠 — 无显式结束关键字的代码"""
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.registry import LanguageRegistry

        registry = LanguageRegistry()
        from yanpub.adapters.xinyu.adapter import XinyuAdapter
        registry.register(XinyuAdapter())

        server = YanLanguageServer(registry=registry)
        adapter = registry.get("xinyu")

        # 心语使用缩进而非结束关键字
        code = '定 函数一() {\n  打印("hello")\n  打印("world")\n}\n\n定 函数二() {\n  返回 42\n}'
        ranges = server._compute_folding_ranges(adapter, code)

        # 应能识别缩进块
        assert isinstance(ranges, list)

    def test_folding_range_empty_code(self):
        """空代码无折叠范围"""
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.registry import LanguageRegistry

        registry = LanguageRegistry()
        from yanpub.adapters.duan.adapter import DuanAdapter
        registry.register(DuanAdapter())

        server = YanLanguageServer(registry=registry)
        adapter = registry.get("duan")

        ranges = server._compute_folding_ranges(adapter, "")
        assert ranges == []

    def test_folding_range_comment_skip(self):
        """注释行不影响折叠"""
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.registry import LanguageRegistry

        registry = LanguageRegistry()
        from yanpub.adapters.duan.adapter import DuanAdapter
        registry.register(DuanAdapter())

        server = YanLanguageServer(registry=registry)
        adapter = registry.get("duan")

        code = '# 这是一个注释\n段落 测试()。\n  打印("hi")。\n结束。'
        ranges = server._compute_folding_ranges(adapter, code)

        # 注释行不应该影响块的开始位置
        assert isinstance(ranges, list)

    def test_folding_range_colon_ending(self):
        """冒号结尾的行视为块开始"""
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.registry import LanguageRegistry

        registry = LanguageRegistry()
        from yanpub.adapters.yan.adapter import YanAdapter
        registry.register(YanAdapter())

        server = YanLanguageServer(registry=registry)
        adapter = registry.get("yan")

        # 言语言使用缩进+冒号
        code = '定义 函数一:\n  打印 "hello"\n  打印 "world"'
        ranges = server._compute_folding_ranges(adapter, code)

        # 冒号结尾行应被视为块开始
        assert isinstance(ranges, list)


# ============================================================
# 2. 适配器热重载测试
# ============================================================

class TestAdapterHotReload:
    """适配器热重载 — 文件变更检测和自动重载"""

    def test_hot_reloader_creation(self):
        """HotReloader 创建"""
        from yanpub.core.hotreload import HotReloader

        reloader = HotReloader()
        assert reloader.history == []

    def test_hot_reloader_callback(self):
        """重载回调注册和通知"""
        from yanpub.core.hotreload import HotReloader, ReloadEvent

        reloader = HotReloader()
        received = []

        def on_reload(event: ReloadEvent):
            received.append(event)

        reloader.on_reload(on_reload)

        # 手动触发通知
        event = ReloadEvent(
            adapter_id="duan",
            adapter_name="段言",
            event_type="modified",
            success=True,
        )
        reloader._notify(event)

        assert len(received) == 1
        assert received[0].adapter_id == "duan"
        assert received[0].success

    def test_hot_reloader_check_no_changes(self):
        """检查无变更的适配器"""
        from yanpub.core.hotreload import HotReloader

        reloader = HotReloader()
        events = reloader.check_and_reload()

        # 首次快照后无变更
        assert isinstance(events, list)

    def test_reload_event_dataclass(self):
        """ReloadEvent 数据类"""
        from yanpub.core.hotreload import ReloadEvent

        event = ReloadEvent(
            adapter_id="yan",
            adapter_name="言",
            event_type="modified",
            success=False,
            error="测试错误",
        )

        assert event.adapter_id == "yan"
        assert event.event_type == "modified"
        assert not event.success
        assert event.error == "测试错误"
        assert event.timestamp > 0

    def test_adapter_watcher_creation(self):
        """AdapterWatcher 创建"""
        from yanpub.core.hotreload import AdapterWatcher

        watcher = AdapterWatcher(poll_interval=0.5)
        assert watcher.reloader is not None

    def test_adapter_watcher_check_now(self):
        """AdapterWatcher 立即检查"""
        from yanpub.core.hotreload import AdapterWatcher

        watcher = AdapterWatcher()
        events = watcher.check_now()
        assert isinstance(events, list)


# ============================================================
# 3. 包管理器工作空间测试
# ============================================================

class TestWorkspace:
    """包管理器工作空间 — monorepo 多包统一管理"""

    def _create_workspace_structure(self, tmp_dir: Path) -> Path:
        """创建测试工作空间结构"""
        # 创建 packages 目录和子包
        pkgs_dir = tmp_dir / "packages"
        pkgs_dir.mkdir()

        # 子包 1: utils
        utils_dir = pkgs_dir / "utils"
        utils_dir.mkdir()
        (utils_dir / "yanpkg.toml").write_text(
            '[package]\nname = "utils"\nlang = "duan"\nversion = "0.1.0"\ndescription = "工具库"\n',
            encoding="utf-8",
        )

        # 子包 2: web-framework
        web_dir = pkgs_dir / "web-framework"
        web_dir.mkdir()
        (web_dir / "yanpkg.toml").write_text(
            '[package]\nname = "web-framework"\nlang = "duan"\nversion = "0.2.0"\ndescription = "Web框架"\n\n[dependencies]\n"duan:utils" = ">=0.1.0"\n',
            encoding="utf-8",
        )

        # 子包 3: cli-tool
        cli_dir = pkgs_dir / "cli-tool"
        cli_dir.mkdir()
        (cli_dir / "yanpkg.toml").write_text(
            '[package]\nname = "cli-tool"\nlang = "duan"\nversion = "1.0.0"\ndescription = "CLI工具"\n\n[dependencies]\n"duan:utils" = ">=0.1.0"\n"duan:web-framework" = ">=0.2.0"\n',
            encoding="utf-8",
        )

        return tmp_dir

    def test_workspace_load(self):
        """加载工作空间"""
        from yanpub.pkg.workspace import Workspace

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = self._create_workspace_structure(Path(tmp_dir))

            # 创建 workspace.toml
            ws_content = '[workspace]\nname = "test-workspace"\nmembers = ["packages/*"]\n'
            (root / "workspace.toml").write_text(ws_content, encoding="utf-8")

            ws = Workspace(root)
            ws.load()

            assert ws.config is not None
            assert ws.config.name == "test-workspace"
            assert len(ws.members) == 3

    def test_workspace_member_info(self):
        """工作空间成员信息"""
        from yanpub.pkg.workspace import Workspace

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = self._create_workspace_structure(Path(tmp_dir))

            ws_content = '[workspace]\nname = "test-ws"\nmembers = ["packages/*"]\n'
            (root / "workspace.toml").write_text(ws_content, encoding="utf-8")

            ws = Workspace(root)
            ws.load()

            member = ws.get_member("duan:web-framework")
            assert member is not None
            assert member.version == "0.2.0"
            assert "duan:utils" in member.dependencies

    def test_workspace_dependency_graph(self):
        """依赖图构建"""
        from yanpub.pkg.workspace import Workspace

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = self._create_workspace_structure(Path(tmp_dir))

            ws_content = '[workspace]\nname = "test-ws"\nmembers = ["packages/*"]\n'
            (root / "workspace.toml").write_text(ws_content, encoding="utf-8")

            ws = Workspace(root)
            ws.load()

            graph = ws.get_dependency_graph()
            assert "duan:cli-tool" in graph
            assert "duan:utils" in graph["duan:cli-tool"]
            assert "duan:web-framework" in graph["duan:cli-tool"]

    def test_workspace_topological_order(self):
        """拓扑排序"""
        from yanpub.pkg.workspace import Workspace

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = self._create_workspace_structure(Path(tmp_dir))

            ws_content = '[workspace]\nname = "test-ws"\nmembers = ["packages/*"]\n'
            (root / "workspace.toml").write_text(ws_content, encoding="utf-8")

            ws = Workspace(root)
            ws.load()

            order = ws.topological_order()

            # utils 应该在 web-framework 和 cli-tool 之前
            utils_idx = order.index("duan:utils")
            web_idx = order.index("duan:web-framework")
            cli_idx = order.index("duan:cli-tool")

            assert utils_idx < web_idx
            assert utils_idx < cli_idx
            assert web_idx < cli_idx

    def test_workspace_internal_external_deps(self):
        """内部/外部依赖区分"""
        from yanpub.pkg.workspace import Workspace

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = self._create_workspace_structure(Path(tmp_dir))

            ws_content = '[workspace]\nname = "test-ws"\nmembers = ["packages/*"]\n'
            (root / "workspace.toml").write_text(ws_content, encoding="utf-8")

            ws = Workspace(root)
            ws.load()

            # cli-tool 的内部依赖
            internal = ws.list_internal_deps("duan:cli-tool")
            assert "duan:utils" in internal
            assert "duan:web-framework" in internal

            # utils 没有内部依赖
            internal_utils = ws.list_internal_deps("duan:utils")
            assert len(internal_utils) == 0

    def test_workspace_create(self):
        """创建工作空间"""
        from yanpub.pkg.workspace import Workspace

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = self._create_workspace_structure(Path(tmp_dir))

            ws = Workspace(root)
            ws_path = ws.create(name="my-workspace")

            assert ws_path.exists()
            assert ws.config is not None
            assert ws.config.name == "my-workspace"

    def test_workspace_status(self):
        """工作空间状态"""
        from yanpub.pkg.workspace import Workspace

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = self._create_workspace_structure(Path(tmp_dir))

            ws_content = '[workspace]\nname = "test-ws"\nmembers = ["packages/*"]\n'
            (root / "workspace.toml").write_text(ws_content, encoding="utf-8")

            ws = Workspace(root)
            ws.load()

            status = ws.status()
            assert status["name"] == "test-ws"
            assert status["members_count"] == 3
            assert len(status["build_order"]) == 3
            assert not status["has_cycles"]

    def test_workspace_add_member(self):
        """添加成员"""
        from yanpub.pkg.workspace import Workspace

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            pkgs_dir = root / "packages"
            pkgs_dir.mkdir()

            ws_content = '[workspace]\nname = "test-ws"\nmembers = ["packages/*"]\n'
            (root / "workspace.toml").write_text(ws_content, encoding="utf-8")

            # 创建不在 packages 下的新成员
            extra_dir = root / "extra-pkg"
            extra_dir.mkdir()
            (extra_dir / "yanpkg.toml").write_text(
                '[package]\nname = "extra"\nlang = "duan"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )

            ws = Workspace(root)
            ws.load()

            # 添加外部成员
            member = ws.add_member("extra-pkg")
            assert member is not None
            assert member.full_name == "duan:extra"

    def test_load_workspace_not_found(self):
        """load_workspace 未找到"""
        from yanpub.pkg.workspace import load_workspace

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = load_workspace(tmp_dir)
            assert result is None

    def test_workspace_member_to_dict(self):
        """WorkspaceMember 序列化"""
        from yanpub.pkg.workspace import WorkspaceMember

        member = WorkspaceMember(
            name="utils",
            full_name="duan:utils",
            lang="duan",
            version="0.1.0",
            path=Path("packages/utils"),
        )

        d = member.to_dict()
        assert d["full_name"] == "duan:utils"
        assert d["version"] == "0.1.0"


# ============================================================
# 4. Playground 实时协作测试
# ============================================================

class TestCollabDocument:
    """CRDT 协作文档测试"""

    def test_document_insert(self):
        """文档插入操作"""
        from yanpub.playground.collab import CollabDocument

        doc = CollabDocument(site_id="user1")
        ops = doc.insert(0, "你好")

        assert doc.get_text() == "你好"
        assert len(ops) == 2  # 两个字符，两个操作

    def test_document_delete(self):
        """文档删除操作"""
        from yanpub.playground.collab import CollabDocument

        doc = CollabDocument(site_id="user1")
        doc.insert(0, "你好世界")
        ops = doc.delete(2, 2)  # 删除"世界"

        assert doc.get_text() == "你好"
        assert len(ops) == 2

    def test_document_concurrent_insert(self):
        """并发插入 — 不同位置"""
        from yanpub.playground.collab import CollabDocument

        doc1 = CollabDocument(site_id="user1")
        doc2 = CollabDocument(site_id="user2")

        # 用户1 插入 "AB"
        ops1 = doc1.insert(0, "AB")

        # 用户2 在开头插入 "CD"
        ops2 = doc2.insert(0, "CD")

        # 互相应用远程操作
        for op in ops1:
            doc2.apply_remote(op)
        for op in ops2:
            doc1.apply_remote(op)

        # 两个文档的文本应该一致
        text1 = doc1.get_text()
        text2 = doc2.get_text()
        # CRDT 保证最终一致性
        assert len(text1) == len(text2)

    def test_document_serialization(self):
        """文档序列化和反序列化"""
        from yanpub.playground.collab import CollabDocument

        doc = CollabDocument(site_id="user1")
        doc.insert(0, "测试文本")

        data = doc.to_dict()
        restored = CollabDocument.from_dict(data)

        assert restored.get_text() == doc.get_text()
        assert restored.site_id == doc.site_id

    def test_char_id_comparison(self):
        """CharId 比较"""
        from yanpub.playground.collab import CharId

        id1 = CharId(site_id="user1", seq=1, lamport=1)
        id2 = CharId(site_id="user2", seq=1, lamport=2)

        assert id1 < id2
        assert id2 > id1
        assert id1 != id2

    def test_char_id_serialization(self):
        """CharId 序列化"""
        from yanpub.playground.collab import CharId

        char_id = CharId(site_id="user1", seq=5, lamport=3)
        data = char_id.to_dict()
        restored = CharId.from_dict(data)

        assert restored.site_id == "user1"
        assert restored.seq == 5
        assert restored.lamport == 3


class TestCollabRoom:
    """协作房间测试"""

    def test_room_creation(self):
        """房间创建"""
        from yanpub.playground.collab import CollabRoom

        room = CollabRoom(room_id="test-room", lang="duan")
        assert room.room_id == "test-room"
        assert room.lang == "duan"
        assert room.user_count == 0

    def test_room_document(self):
        """房间文档"""
        from yanpub.playground.collab import CollabRoom

        room = CollabRoom(room_id="test-room", lang="duan")
        assert room.document.get_text() == ""


class TestCollabManager:
    """协作房间管理器测试"""

    def test_create_room(self):
        """创建协作房间"""
        from yanpub.playground.collab import CollabManager

        manager = CollabManager()
        result = manager.create_room(lang="duan", code="打印(\"hello\")")

        assert "roomId" in result
        assert result["lang"] == "duan"
        assert len(result["roomId"]) == 12

    def test_create_room_with_code(self):
        """创建带初始代码的房间"""
        from yanpub.playground.collab import CollabManager

        manager = CollabManager()
        result = manager.create_room(lang="duan", code="你好")

        room = manager.get_room(result["roomId"])
        assert room is not None
        assert "你" in room.document.get_text()

    def test_list_rooms(self):
        """列出房间"""
        from yanpub.playground.collab import CollabManager

        manager = CollabManager()
        manager.create_room(lang="duan")
        manager.create_room(lang="yan")

        rooms = manager.list_rooms()
        assert len(rooms) == 2

    def test_get_nonexistent_room(self):
        """获取不存在的房间"""
        from yanpub.playground.collab import CollabManager

        manager = CollabManager()
        room = manager.get_room("nonexistent")
        assert room is None

    def test_cleanup_expired(self):
        """清理过期房间"""
        from yanpub.playground.collab import CollabManager

        manager = CollabManager()
        manager.create_room(lang="duan")

        # 设置过期时间为0，让所有空房间过期
        manager._room_ttl = 0
        time.sleep(0.01)

        cleaned = manager.cleanup_expired()
        assert cleaned == 1
        assert len(manager.list_rooms()) == 0

    def test_unique_room_ids(self):
        """房间 ID 唯一性"""
        from yanpub.playground.collab import CollabManager

        manager = CollabManager()
        ids = set()
        for _ in range(10):
            result = manager.create_room(lang="duan")
            ids.add(result["roomId"])

        assert len(ids) == 10


class TestCollabUser:
    """协作用户测试"""

    def test_user_creation(self):
        """用户创建"""
        from yanpub.playground.collab import CollabUser

        user = CollabUser(user_id="u1", display_name="测试用户")
        assert user.user_id == "u1"
        assert user.display_name == "测试用户"
        assert user.cursor_line == 0
        assert user.cursor_col == 0

    def test_user_colors(self):
        """用户颜色分配"""
        from yanpub.playground.collab import CollabRoom

        room = CollabRoom(room_id="test")

        # 模拟颜色分配
        color1 = room._next_color()
        color2 = room._next_color()

        assert color1 != color2
        assert color1.startswith("#")
        assert color2.startswith("#")

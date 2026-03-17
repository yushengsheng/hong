from __future__ import annotations


TEXT_HEADER = "# 宏脚本文本格式 v4"
TEXT_EVENTS_MARKER = "事件:"

TEXT_MOUSE_TAP = "鼠标点击"
TEXT_MOUSE_DRAG = "鼠标拖拽"
TEXT_MOUSE_SCROLL = "鼠标滚轮"
TEXT_KEY_PRESS = "键盘按下"
TEXT_KEY_RELEASE = "键盘松开"
TEXT_KEY_EVENT_LABELS = {
    "key_press": TEXT_KEY_PRESS,
    "key_release": TEXT_KEY_RELEASE,
}
TEXT_KEY_EVENT_KINDS = {value: key for key, value in TEXT_KEY_EVENT_LABELS.items()}

BUTTON_LABELS = {
    "left": "左键",
    "right": "右键",
    "middle": "中键",
    "x1": "侧键1",
    "x2": "侧键2",
}
BUTTON_NAMES = {value: key for key, value in BUTTON_LABELS.items()}

PRESS_LABELS = {
    True: "按下",
    False: "松开",
}
PRESS_VALUES = {value: key for key, value in PRESS_LABELS.items()}

VISIBLE_CHARACTERS = {
    " ": "<空格>",
    "\t": "<Tab>",
    "\n": "<换行>",
}
VISIBLE_CHARACTER_VALUES = {value: key for key, value in VISIBLE_CHARACTERS.items()}

TEXT_METADATA_KEYS = (
    "名称",
    "创建时间",
    "版本",
    "屏幕尺寸",
    "屏幕原点",
    "默认循环次数",
    "默认播放速度",
    "全局快捷键",
    "自定义排序",
    "事件数",
)

TEXT_HEADER_COMMENTS = (
    TEXT_HEADER,
    "# 每一行只保留一个动作节点，不写入鼠标移动轨迹。",
    "# “间隔”表示距离上一条动作的等待秒数。",
    "# “默认循环次数”和“默认播放速度”会在列表播放时直接生效。",
    "# “全局快捷键”格式示例：Ctrl+Alt+1 / Ctrl+Shift+F2。",
    "# “自定义排序”留空时按录制时间排序，填写数字时按数字从小到大排。",
    "# 修改 x/y 后，加载时会自动重算比例坐标，方便跨 1K、2K、4K 屏幕适配。",
    "# 键盘按键格式：字符:a / 特殊:enter / 虚拟键:13",
)

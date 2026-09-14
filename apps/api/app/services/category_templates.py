"""Editable starter taxonomies, not official industry classification standards."""

TEMPLATES = {
    "nonstandard": {
        "code": "NS", "name": "非标制造", "groups": {
            "01": ("机械加工件", ["车削件", "铣削件", "钣金焊接件", "工装夹具"]),
            "02": ("传动与标准件", ["轴承", "直线导轨丝杠", "联轴器齿轮", "紧固件"]),
            "03": ("电气与控制", ["PLC与控制器", "伺服电机驱动器", "传感器", "低压电气线缆"]),
            "04": ("气动与液压", ["气缸", "电磁阀", "液压泵阀", "管接头与密封"]),
            "05": ("原材料与辅料", ["钢材", "铝材", "工程塑料", "润滑与耗材"]),
        },
    },
    "automotive": {
        "code": "AUTO", "name": "汽车零部件制造", "groups": {
            "01": ("金属原材料", ["钢板钢带", "铝合金", "铸锻毛坯", "铜材"]),
            "02": ("动力与传动部件", ["齿轮轴类", "轴承", "壳体", "密封件"]),
            "03": ("底盘与车身部件", ["冲压件", "焊接总成", "悬架连接件", "制动部件"]),
            "04": ("电子电气部件", ["线束连接器", "传感器", "控制模块", "电机组件"]),
            "05": ("工艺与工装", ["模具夹具", "切削刀具", "表面处理材料", "检测量具"]),
        },
    },
}


def template_rows(industry: str) -> list[dict]:
    template = TEMPLATES[industry]
    root = template["code"]
    rows = [{"code": root, "name": template["name"], "parent_code": None, "level": 1}]
    for segment, (name, leaves) in template["groups"].items():
        parent = f"{root}-{segment}"
        rows.append({"code": parent, "name": name, "parent_code": root, "level": 2})
        for index, leaf in enumerate(leaves, 1):
            rows.append({"code": f"{parent}-{index:02d}", "name": leaf, "parent_code": parent, "level": 3})
    return rows

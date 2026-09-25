"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class LocationImportPayload(BaseModel):
    """场地租用文件导入请求：内容直接随 JSON 提交，便于失败后按行续传。"""

    filename: str
    content: str
    keyword: str | None = None
    name: str | None = None
    location_type: str | None = None
    status: str | None = None
    start_row: int = Field(default=0, ge=0)


class LocationImportRowResult(BaseModel):
    row: int
    status: str
    reason: str | None = None
    entry: dict[str, Any] | None = None


class LocationImportResult(BaseModel):
    ok: bool
    message: str
    total: int = 0
    processed: int = 0
    created: int = 0
    duplicates: int = 0
    failed: int = 0
    interrupted: bool = False
    resume_from: int | None = None
    file_fingerprint: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    rows: list[LocationImportRowResult] = Field(default_factory=list)



class ScriptEntry(BaseModel):
    """剧本明细结构。"""

    field_0: str | None = None  # 剧本编号
    field_1: str | None = None  # 剧本名称
    field_2: str | None = None  # 题材类型
    field_3: str | None = None  # 编剧姓名
    field_4: str | None = None  # 总集数
    field_5: str | None = None  # 当前版本
    field_6: str | None = None  # 终稿日期
    field_7: str | None = None  # 版权归属

class SceneEntry(BaseModel):
    """分场表明细结构。"""

    field_0: str | None = None  # 场次编号
    field_1: str | None = None  # 所属剧本
    field_2: str | None = None  # 场景地点
    field_3: str | None = None  # 日戏夜戏
    field_4: str | None = None  # 出场人物
    field_5: str | None = None  # 预计时长
    field_6: str | None = None  # 拍摄难度
    field_7: str | None = None  # 分场状态

class CastingEntry(BaseModel):
    """角色明细结构。"""

    field_0: str | None = None  # 角色编号
    field_1: str | None = None  # 角色名称
    field_2: str | None = None  # 角色类型
    field_3: str | None = None  # 候选演员
    field_4: str | None = None  # 试镜日期
    field_5: str | None = None  # 片酬区间
    field_6: str | None = None  # 签约状态
    field_7: str | None = None  # 角色说明

class CrewEntry(BaseModel):
    """剧组成员明细结构。"""

    field_0: str | None = None  # 成员编号
    field_1: str | None = None  # 姓名
    field_2: str | None = None  # 岗位职务
    field_3: str | None = None  # 所属组别
    field_4: str | None = None  # 联系电话
    field_5: str | None = None  # 进场日期
    field_6: str | None = None  # 离场日期
    field_7: str | None = None  # 在组状态

class NoticeEntry(BaseModel):
    """拍摄通告单明细结构。"""

    field_0: str | None = None  # 通告编号
    field_1: str | None = None  # 拍摄日期
    field_2: str | None = None  # 集合时间
    field_3: str | None = None  # 拍摄地点
    field_4: str | None = None  # 拍摄场次
    field_5: str | None = None  # 出勤人员
    field_6: str | None = None  # 用车安排
    field_7: str | None = None  # 通告状态

class LocationEntry(BaseModel):
    """拍摄场地明细结构。"""

    field_0: str | None = None  # 场地编号
    field_1: str | None = None  # 场地名称
    field_2: str | None = None  # 场地类型
    field_3: str | None = None  # 所属区域
    field_4: str | None = None  # 可租时段
    field_5: str | None = None  # 场地费用
    field_6: str | None = None  # 对接联系人
    field_7: str | None = None  # 租用状态

class PropEntry(BaseModel):
    """道具明细结构。"""

    field_0: str | None = None  # 道具编号
    field_1: str | None = None  # 道具名称
    field_2: str | None = None  # 道具类别
    field_3: str | None = None  # 所属场次
    field_4: str | None = None  # 保管人员
    field_5: str | None = None  # 采购单价
    field_6: str | None = None  # 使用状态
    field_7: str | None = None  # 归还日期

class CostumeEntry(BaseModel):
    """戏服明细结构。"""

    field_0: str | None = None  # 服装编号
    field_1: str | None = None  # 服装名称
    field_2: str | None = None  # 角色归属
    field_3: str | None = None  # 尺码规格
    field_4: str | None = None  # 造型师
    field_5: str | None = None  # 使用场次
    field_6: str | None = None  # 当前状态
    field_7: str | None = None  # 清洗记录

class MakeupEntry(BaseModel):
    """妆造方案明细结构。"""

    field_0: str | None = None  # 方案编号
    field_1: str | None = None  # 角色名称
    field_2: str | None = None  # 造型风格
    field_3: str | None = None  # 特效需求
    field_4: str | None = None  # 化妆师
    field_5: str | None = None  # 试妆日期
    field_6: str | None = None  # 定妆照片
    field_7: str | None = None  # 方案状态

class EquipmentEntry(BaseModel):
    """拍摄器材明细结构。"""

    field_0: str | None = None  # 器材编号
    field_1: str | None = None  # 器材名称
    field_2: str | None = None  # 器材类别
    field_3: str | None = None  # 品牌型号
    field_4: str | None = None  # 所属租赁商
    field_5: str | None = None  # 日租金
    field_6: str | None = None  # 领用人员
    field_7: str | None = None  # 器材状态

class ShootingEntry(BaseModel):
    """拍摄日明细结构。"""

    field_0: str | None = None  # 拍摄日编号
    field_1: str | None = None  # 拍摄日期
    field_2: str | None = None  # 拍摄地点
    field_3: str | None = None  # 计划场次
    field_4: str | None = None  # 完成场次
    field_5: str | None = None  # 有效工时
    field_6: str | None = None  # 超时情况
    field_7: str | None = None  # 拍摄状态

class FootageEntry(BaseModel):
    """拍摄素材明细结构。"""

    field_0: str | None = None  # 素材编号
    field_1: str | None = None  # 素材类型
    field_2: str | None = None  # 拍摄日期
    field_3: str | None = None  # 文件大小
    field_4: str | None = None  # 存储介质
    field_5: str | None = None  # 转码格式
    field_6: str | None = None  # 备份位置
    field_7: str | None = None  # 素材状态

class EditEntry(BaseModel):
    """剪辑任务明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 所属集数
    field_2: str | None = None  # 剪辑师
    field_3: str | None = None  # 粗剪版本
    field_4: str | None = None  # 精剪版本
    field_5: str | None = None  # 交付日期
    field_6: str | None = None  # 修改轮次
    field_7: str | None = None  # 剪辑状态

class VfxEntry(BaseModel):
    """特效镜头明细结构。"""

    field_0: str | None = None  # 镜头编号
    field_1: str | None = None  # 所属集数
    field_2: str | None = None  # 特效类型
    field_3: str | None = None  # 制作供应商
    field_4: str | None = None  # 渲染帧数
    field_5: str | None = None  # 预估工时
    field_6: str | None = None  # 交付版本
    field_7: str | None = None  # 制作状态

class ReviewEntry(BaseModel):
    """审片记录明细结构。"""

    field_0: str | None = None  # 审片编号
    field_1: str | None = None  # 审片轮次
    field_2: str | None = None  # 审片人
    field_3: str | None = None  # 审片对象
    field_4: str | None = None  # 问题类型
    field_5: str | None = None  # 修改意见
    field_6: str | None = None  # 回复说明
    field_7: str | None = None  # 审片状态

class BudgetEntry(BaseModel):
    """预算科目明细结构。"""

    field_0: str | None = None  # 科目编号
    field_1: str | None = None  # 科目名称
    field_2: str | None = None  # 费用类别
    field_3: str | None = None  # 预算金额
    field_4: str | None = None  # 已用金额
    field_5: str | None = None  # 剩余额度
    field_6: str | None = None  # 审批人
    field_7: str | None = None  # 科目状态

class ExpenseEntry(BaseModel):
    """报销单明细结构。"""

    field_0: str | None = None  # 报销单号
    field_1: str | None = None  # 报销人
    field_2: str | None = None  # 费用类别
    field_3: str | None = None  # 发生日期
    field_4: str | None = None  # 报销金额
    field_5: str | None = None  # 票据张数
    field_6: str | None = None  # 所属科目
    field_7: str | None = None  # 报销状态

class ScheduleEntry(BaseModel):
    """演员档期明细结构。"""

    field_0: str | None = None  # 档期编号
    field_1: str | None = None  # 演员姓名
    field_2: str | None = None  # 经纪公司
    field_3: str | None = None  # 可用起止日
    field_4: str | None = None  # 每日工时上限
    field_5: str | None = None  # 档期费用
    field_6: str | None = None  # 协调人
    field_7: str | None = None  # 档期状态

class PermitEntry(BaseModel):
    """拍摄许可明细结构。"""

    field_0: str | None = None  # 许可编号
    field_1: str | None = None  # 许可类型
    field_2: str | None = None  # 申请地点
    field_3: str | None = None  # 受理单位
    field_4: str | None = None  # 申请日期
    field_5: str | None = None  # 有效期至
    field_6: str | None = None  # 许可费用
    field_7: str | None = None  # 许可状态

class WrapEntry(BaseModel):
    """结算单明细结构。"""

    field_0: str | None = None  # 结算单号
    field_1: str | None = None  # 结算对象
    field_2: str | None = None  # 结算周期
    field_3: str | None = None  # 应结金额
    field_4: str | None = None  # 已付金额
    field_5: str | None = None  # 未付金额
    field_6: str | None = None  # 结算人
    field_7: str | None = None  # 结算状态

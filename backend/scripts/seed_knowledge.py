"""
Seed script: ingest sample medical aesthetics documents into the knowledge base.

Usage:
    cd Q:/Cosmetic/backend
    python -m scripts.seed_knowledge
"""
import asyncio
from app.core.database import get_engine, get_session_factory, Base
from app.services.rag import ingest_document

SEED_DOCS = [
    {
        "title": "玻尿酸注射填充",
        "category": "projects",
        "authority_level": 2,
        "source": "医美科普百科",
        "content": """玻尿酸（透明质酸，Hyaluronic Acid，简称 HA）是目前最常用的注射填充材料之一。

适应症：鼻基底凹陷、泪沟、法令纹、丰唇、丰下巴、太阳穴凹陷等软组织填充。

常见品牌：乔雅登（Juvederm）、瑞蓝（Restylane）、伊婉（Yvoire）、海薇、润百颜等。需认准 NMPA 批准的正规产品。

维持时间：根据产品分子量和交联程度不同，通常维持 6-18 个月。大分子产品维持更久，小分子更适合精细部位。

风险与并发症：
- 常见：注射部位红肿、淤青、轻微疼痛（通常 1-3 天消退）
- 少见：结节、不对称、过度填充
- 严重（罕见）：血管栓塞导致皮肤坏死或失明（需选择经验丰富的医生）

禁忌症：
- 孕期/哺乳期
- 注射部位有感染或炎症
- 对透明质酸过敏
- 自身免疫性疾病活动期

术后护理：
- 24 小时内避免剧烈运动、高温环境（桑拿、温泉）
- 一周内避免按压注射部位
- 如出现剧烈疼痛、皮肤发白/发紫，立即就医

价格参考：根据品牌和用量，单次约 1500-8000 元不等。""",
    },
    {
        "title": "肉毒素注射（瘦脸针/除皱针）",
        "category": "projects",
        "authority_level": 2,
        "source": "医美科普百科",
        "content": """肉毒素（Botulinum Toxin）通过抑制神经末梢释放乙酰胆碱，使肌肉暂时性放松，达到除皱或瘦脸效果。

适应症：
- 动态皱纹：额纹、眉间纹（川字纹）、鱼尾纹
- 咬肌肥大（方脸→瘦脸）
- 腋下多汗症
- 小腿肌肉发达

常见品牌：保妥适（Botox，美国艾尔建）、衡力（中国兰州生物制品研究所）、乐提葆（Letybo，韩国）。

维持时间：通常 3-6 个月。首次注射后肌肉记忆逐渐减弱，多次注射后间隔可延长。

风险与并发症：
- 常见：注射点轻微疼痛、小面积淤青
- 少见：表情不自然、咀嚼无力（咬肌注射后）、眉下垂
- 注意：肉毒素剂量和注射位置至关重要，必须由有资质的医生操作

禁忌症：
- 孕期/哺乳期
- 重症肌无力等神经肌肉疾病
- 对肉毒素蛋白过敏
- 注射部位感染

术后护理：
- 4-6 小时内不要躺下，避免按揉注射区域
- 一周内避免剧烈运动
- 效果通常在注射后 3-7 天逐渐显现

价格参考：根据品牌和注射部位，单次约 800-5000 元。""",
    },
    {
        "title": "热玛吉（Thermage）",
        "category": "projects",
        "authority_level": 2,
        "source": "医美科普百科",
        "content": """热玛吉（Thermage）是一种非侵入性射频紧肤治疗，利用单极射频技术加热真皮层和皮下组织，刺激胶原蛋白收缩和新生。

适应症：
- 面部皮肤松弛、轮廓下垂
- 眼周细纹、眼袋松弛（眼部专用治疗头）
- 颈部松弛
- 身体松弛（腹部、手臂等）

适合年龄：25-65 岁，皮肤有轻到中度松弛者效果最佳。严重松弛建议考虑手术。

治疗过程：
- 单次治疗约 45-90 分钟
- 治疗时有热感和轻微刺痛，可耐受
- 无创，无恢复期，治疗后可正常活动

效果与维持：
- 即时效果：胶原收缩带来的轻微紧致
- 远期效果：2-6 个月后胶原新生，紧致效果最佳
- 维持时间：约 1-2 年，因个人体质和保养而异

风险与并发症：
- 常见：治疗后面部轻微红肿（数小时消退）
- 少见：水肿、轻微灼伤
- 注意：必须使用正品治疗头（注意辨别假货），由认证医师操作

禁忌症：
- 体内有金属植入物或电子设备（如心脏起搏器）
- 孕期
- 治疗区域有开放性伤口
- 严重皮肤病

价格参考：全面部治疗约 15000-35000 元（含正品治疗头）。""",
    },
    {
        "title": "光子嫩肤（IPL/强脉冲光）",
        "category": "projects",
        "authority_level": 2,
        "source": "医美科普百科",
        "content": """光子嫩肤（Intense Pulsed Light，IPL）利用强脉冲光的选择性光热作用，针对不同色基（黑色素、血红蛋白）进行治疗。

适应症：
- 色素问题：雀斑、日晒斑、浅层色沉
- 血管问题：红血丝、酒糟鼻早期、毛细血管扩张
- 肤质改善：毛孔粗大、肤色不均、轻度痘印
- 光老化综合改善

治疗方案：
- 通常建议 3-5 次为一疗程
- 每次间隔 3-4 周
- 单次治疗约 20-30 分钟

效果：
- 首次治疗后即可看到色斑变深结痂（3-7 天脱落）
- 红血丝改善需多次治疗
- 整体肤质提升在疗程后最明显

术后护理：
- 严格防晒（SPF50+ 防晒霜，至少 4 周）
- 治疗后 3 天内避免使用刺激性护肤品（酸类、酒精）
- 加强保湿
- 治疗部位色斑结痂后自然脱落，不要人为剥除

禁忌症：
- 近期暴晒或皮肤有晒伤
- 光敏性疾病或正在使用光敏药物
- 孕期
- 深肤色人群需谨慎（易出现色素沉着）

价格参考：单次约 800-3000 元，疗程价更优惠。""",
    },
    {
        "title": "超声炮/超声刀（HIFU）",
        "category": "projects",
        "authority_level": 2,
        "source": "医美科普百科",
        "content": """超声刀（High Intensity Focused Ultrasound，HIFU）利用高强度聚焦超声波，将能量精准作用于皮肤 SMAS 筋膜层，产生热凝固点，刺激胶原蛋白重塑。

适应症：
- 面部松弛下垂（法令纹加深、下颌线模糊）
- 双下巴
- 颈部松弛

常见设备：美版超声刀（Ultherapy，FDA 认证）、韩版超声炮等。注意国内部分超声刀设备未获 NMPA 批准。

治疗过程：
- 治疗时间约 30-60 分钟
- 疼痛感明显（特别是骨骼附近），可配合局部麻醉
- 无创，术后可能面部轻微红肿

效果与维持：
- 效果在 1-3 个月后逐渐显现
- 最佳效果在 3-6 个月
- 维持约 1-2 年

风险与并发症：
- 常见：疼痛、红肿、轻微水肿
- 少见：暂时性面部麻木、轻微灼伤
- 严重（操作不当）：神经损伤、脂肪液化

禁忌症：
- 面部有金属植入物
- 严重囊肿型痤疮
- 开放性伤口
- 孕期
- 面部脂肪过少者（可能加重凹陷）

价格参考：全面部约 8000-30000 元，因设备和机构而异。""",
    },
]


async def main():
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as db:
        for doc in SEED_DOCS:
            await ingest_document(
                db=db,
                title=doc["title"],
                content=doc["content"],
                source=doc["source"],
                category=doc["category"],
                authority_level=doc["authority_level"],
            )
    print(f"✓ Seeded {len(SEED_DOCS)} documents into knowledge base")


if __name__ == "__main__":
    asyncio.run(main())

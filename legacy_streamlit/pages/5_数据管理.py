"""校园数据来源、刷新、导入、核验和版本回滚页。"""

from __future__ import annotations

from dataclasses import asdict
import hmac

import streamlit as st

from config import get_admin_token
from core.models import CAMPUSES, LOCATION_CATEGORIES, CanteenInfo, CampusLocation, SourceReference
from core.time_service import format_current_time_prompt, now_china
from services.campus_data_service import CampusDataService, SOURCE_LEVEL_LABELS
from services.location_service import LocationService
from ui.navigation import safe_page_link


st.set_page_config(page_title="数据管理 - 广金大师兄", page_icon="🛠️", layout="wide")


@st.cache_resource
def get_services():
    locations = LocationService()
    return locations, CampusDataService(locations.database.path)


locations, data_service = get_services()
st.title("🛠️ 校园数据管理")
st.caption(format_current_time_prompt())
admin_token = get_admin_token()
if not admin_token:
    st.error("未配置 GDUF_ADMIN_TOKEN，数据管理页已锁定。请通过 Streamlit Secrets 或环境变量配置，不要把 Token 写入仓库。")
    st.stop()
if not st.session_state.get("admin_authenticated"):
    entered_token = st.text_input("管理员 Token", type="password")
    if st.button("验证管理员身份"):
        if hmac.compare_digest(entered_token, admin_token):
            st.session_state.admin_authenticated = True
            st.rerun()
        else:
            st.error("Token 不正确。")
    st.stop()
st.warning("该页会修改本地数据库。生产部署还应在网关层限制为管理员访问。")

with st.sidebar:
    safe_page_link("app.py", "返回首页")
    campus = st.selectbox("校区", CAMPUSES)

status_tab, refresh_tab, edit_tab, import_tab, review_tab = st.tabs(
    ["数据状态", "官方源刷新", "新增与编辑", "批量导入", "核验与回滚"]
)

with status_tab:
    entries = locations.search_locations(campus=campus, include_inactive=True)
    stale = locations.list_stale_locations(campus)
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("地点总数", len(entries))
    col_b.metric("启用条目", sum(item.is_active for item in entries))
    col_c.metric("待核验/过期", len(stale))
    st.dataframe(
        [
            {
                "ID": item.id,
                "名称": item.name,
                "分类": item.category,
                "数据状态": item.data_status,
                "新鲜度": item.freshness_status,
                "核验时间": item.verified_at or "",
                "启用": item.is_active,
            }
            for item in entries
        ],
        width="stretch",
        hide_index=True,
    )
    st.subheader("来源缓存")
    source_rows = data_service.list_sources(campus)
    if source_rows:
        st.dataframe(
            [
                {
                    "标题": row["title"],
                    "URL": row["url"],
                    "级别": SOURCE_LEVEL_LABELS.get(row["source_level"], row["source_level"]),
                    "发布日期": row.get("published_at") or "未提取",
                    "抓取时间": row.get("fetched_at") or "未抓取",
                    "状态": row.get("source_status"),
                    "最后错误": row.get("last_error") or "",
                }
                for row in source_rows
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("还没有刷新过该校区的官方源。")

with refresh_tab:
    st.write("按官网/校区官网 → 职能部门 → 管理员实地核验的优先级管理来源。")
    force = st.checkbox("忽略 6 小时缓存并强制刷新")
    if st.button("刷新当前校区官方源", type="primary"):
        with st.spinner("正在逐个刷新；单个源失败不会影响其他源……"):
            results = data_service.refresh_official_sources(campus=campus, force=force)
        st.dataframe(results, width="stretch", hide_index=True)
        if any(item["status"].startswith("failed") for item in results):
            st.warning("有来源刷新失败；如已有缓存，旧数据已保留。")
        if any(item.get("changed") for item in results):
            st.info("检测到网页内容变化。它只进入待核验来源缓存，不会自动覆盖地点事实。")

with edit_tab:
    st.subheader("新增或编辑地点/饭堂")
    existing_locations = locations.search_locations(campus=campus, include_inactive=True)
    edit_location_id = st.selectbox(
        "选择现有条目，或新建",
        [""] + [item.id for item in existing_locations],
        format_func=lambda value: "＋ 新建地点/饭堂"
        if not value
        else next(item.name for item in existing_locations if item.id == value),
    )
    current_location = next(
        (item for item in existing_locations if item.id == edit_location_id),
        None,
    )
    current_source = current_location.source_references[0] if current_location and current_location.source_references else None
    with st.form("location-editor"):
        location_id = st.text_input("ID", value=current_location.id if current_location else "")
        location_name = st.text_input("名称", value=current_location.name if current_location else "")
        aliases = st.text_input("别名（用 | 分隔）", value="|".join(current_location.aliases) if current_location else "")
        category = st.selectbox(
            "分类",
            LOCATION_CATEGORIES,
            index=LOCATION_CATEGORIES.index(current_location.category) if current_location else 0,
        )
        description = st.text_area("描述", value=current_location.description if current_location else "")
        area = st.text_input("区域", value=current_location.area if current_location else "")
        building = st.text_input("建筑", value=current_location.building if current_location else "")
        floor = st.text_input("楼层", value=current_location.floor if current_location else "")
        address = st.text_input("地址", value=current_location.address if current_location else "")
        opening_hours = st.text_input("开放/营业时间", value=current_location.opening_hours if current_location else "")
        phone = st.text_input("电话", value=current_location.phone if current_location else "")
        services_text = st.text_input("服务（用 | 分隔）", value="|".join(current_location.services) if current_location else "")
        payment_text = st.text_input("支付方式（用 | 分隔）", value="|".join(current_location.payment_methods) if current_location else "")
        use_gps = st.checkbox("已核对 GPS 坐标", value=bool(current_location and current_location.latitude is not None))
        latitude = st.number_input("纬度", value=float(current_location.latitude or 0.0) if current_location else 0.0, format="%.7f")
        longitude = st.number_input("经度", value=float(current_location.longitude or 0.0) if current_location else 0.0, format="%.7f")
        use_schematic = st.checkbox("使用 0–1 示意坐标", value=bool(current_location and current_location.map_x is not None) if current_location else True)
        map_x = st.number_input("map_x", min_value=0.0, max_value=1.0, value=float(current_location.map_x or 0.5) if current_location else 0.5)
        map_y = st.number_input("map_y", min_value=0.0, max_value=1.0, value=float(current_location.map_y or 0.5) if current_location else 0.5)
        source_title = st.text_input("来源标题", value=current_source.title if current_source else "")
        source_url = st.text_input("来源 URL", value=current_source.url if current_source else "")
        source_publisher = st.text_input("发布机构", value=current_source.publisher if current_source else "")
        source_published = st.text_input("发布日期", value=(current_source.published_at or "") if current_source else "")
        source_level = st.number_input("来源等级", min_value=1, max_value=8, value=current_source.source_level if current_source else 5)
        source_official = st.checkbox("官方来源", value=current_source.is_official if current_source else False)
        confidence = st.slider("置信度", 0.0, 1.0, float(current_location.confidence if current_location else 0.0), 0.05)
        data_status = st.selectbox(
            "数据状态",
            ("needs_verification", "verified", "historical_seed", "demo_fixture"),
            index=("needs_verification", "verified", "historical_seed", "demo_fixture").index(current_location.data_status)
            if current_location and current_location.data_status in ("needs_verification", "verified", "historical_seed", "demo_fixture")
            else 0,
        )
        location_confirmed = st.checkbox("我已核对以上信息和来源")
        save_location = st.form_submit_button("保存地点/饭堂", disabled=not location_confirmed)
    if save_location:
        if not location_id.strip() or not location_name.strip():
            st.error("ID 和名称不能为空。")
        else:
            source_references = []
            if source_title.strip() or source_url.strip():
                source_references = [
                    SourceReference(
                        title=source_title.strip() or source_url.strip(),
                        url=source_url.strip(),
                        publisher=source_publisher.strip(),
                        published_at=source_published.strip() or None,
                        fetched_at=current_source.fetched_at if current_source else None,
                        source_level=int(source_level),
                        is_official=source_official,
                        source_status="current_source" if data_status == "verified" else "unverified",
                    )
                ]
            item = CampusLocation(
                id=location_id.strip(),
                name=location_name.strip(),
                aliases=[value.strip() for value in aliases.split("|") if value.strip()],
                campus=campus,
                category=category,
                description=description.strip(),
                building=building.strip(),
                floor=floor.strip(),
                area=area.strip(),
                latitude=float(latitude) if use_gps else None,
                longitude=float(longitude) if use_gps else None,
                map_x=float(map_x) if use_schematic else None,
                map_y=float(map_y) if use_schematic else None,
                address=address.strip(),
                opening_hours=opening_hours.strip(),
                phone=phone.strip(),
                services=[value.strip() for value in services_text.split("|") if value.strip()],
                payment_methods=[value.strip() for value in payment_text.split("|") if value.strip()],
                source_references=source_references,
                verification_method=current_location.verification_method if current_location else "admin_pending",
                verified_at=current_location.verified_at if current_location else None,
                confidence=confidence,
                is_active=current_location.is_active if current_location else True,
                data_status=data_status,
                created_at=current_location.created_at if current_location else None,
            )
            locations.save_location(item, changed_by="admin-ui")
            st.success("已保存；如果是更新，旧版本已记录。")

    st.subheader("新增或编辑饭堂档口")
    canteens = locations.list_canteens(campus)
    campus_stalls = locations.list_food_stalls(campus=campus, include_inactive=True)
    if not canteens:
        st.info("请先在上方创建 category=canteen 的饭堂。")
    else:
        edit_stall_id = st.selectbox(
            "选择现有档口，或新建",
            [""] + [item.id for item in campus_stalls],
            format_func=lambda value: "＋ 新建档口" if not value else next(item.name for item in campus_stalls if item.id == value),
        )
        current_stall = next((item for item in campus_stalls if item.id == edit_stall_id), None)
        with st.form("stall-editor"):
            stall_id_value = st.text_input("档口 ID", value=current_stall.id if current_stall else "")
            canteen_id = st.selectbox(
                "所属饭堂",
                [item.id for item in canteens],
                index=next((index for index, item in enumerate(canteens) if current_stall and item.id == current_stall.canteen_id), 0),
                format_func=lambda value: next(item.name for item in canteens if item.id == value),
            )
            stall_name = st.text_input("档口名", value=current_stall.name if current_stall else "")
            stall_floor = st.text_input("档口楼层", value=current_stall.floor if current_stall else "")
            food_type = st.text_input("餐饮类型", value=current_stall.food_type if current_stall else "")
            common_items = st.text_input("常见餐品（用 | 分隔）", value="|".join(current_stall.common_items) if current_stall else "")
            price_range = st.text_input("价格范围", value=current_stall.price_range if current_stall else "")
            meal_periods = st.multiselect("餐段", ["早餐", "午餐", "晚餐", "夜宵"], default=current_stall.meal_periods if current_stall else [])
            stall_hours = st.text_input("营业时间", value=current_stall.opening_hours if current_stall else "")
            stall_payments = st.text_input("支付方式（用 | 分隔）", value="|".join(current_stall.payment_methods) if current_stall else "")
            operating_label = st.selectbox(
                "是否营业",
                ("待核验", "是", "否"),
                index=0 if not current_stall or current_stall.is_operating is None else (1 if current_stall.is_operating else 2),
            )
            stall_verified = st.checkbox("本次已实地核验档口")
            stall_confirmed = st.checkbox("我已核对档口和常见餐品，它们不代表今日菜单")
            save_stall = st.form_submit_button("保存档口", disabled=not stall_confirmed)
        if save_stall:
            if not stall_id_value.strip() or not stall_name.strip():
                st.error("档口 ID 和名称不能为空。")
            else:
                operating = None if operating_label == "待核验" else operating_label == "是"
                stall_item = CanteenInfo(
                    id=stall_id_value.strip(),
                    canteen_id=canteen_id,
                    name=stall_name.strip(),
                    campus=campus,
                    floor=stall_floor.strip(),
                    food_type=food_type.strip(),
                    common_items=[value.strip() for value in common_items.split("|") if value.strip()],
                    price_range=price_range.strip(),
                    meal_periods=meal_periods,
                    opening_hours=stall_hours.strip(),
                    payment_methods=[value.strip() for value in stall_payments.split("|") if value.strip()],
                    is_operating=operating,
                    verified_at=now_china().isoformat() if stall_verified else (current_stall.verified_at if current_stall else None),
                    source_references=current_stall.source_references if current_stall else [],
                    confidence=max(current_stall.confidence if current_stall else 0.0, 0.85 if stall_verified else 0.0),
                    data_status="verified" if stall_verified else (current_stall.data_status if current_stall else "needs_verification"),
                    is_active=current_stall.is_active if current_stall else True,
                    created_at=current_stall.created_at if current_stall else None,
                )
                locations.save_food_stall(stall_item)
                st.success("已保存档口。")

    st.subheader("上传校园底图")
    map_upload = st.file_uploader("选择 PNG/JPG/WebP（最大 10 MB）", type=["png", "jpg", "jpeg", "webp"], key="campus-map-upload")
    map_confirmed = st.checkbox("我已确认图片授权、校区和版本")
    if st.button("上传并设为当前底图", disabled=map_upload is None or not map_confirmed):
        try:
            record = locations.save_campus_map(campus, map_upload.name, map_upload.getvalue())
            st.success(f"已上传，时间：{record['uploaded_at']}。")
        except ValueError as exc:
            st.error(str(exc))

with import_tab:
    st.write("支持 CSV、JSON 和 GeoJSON。每条必须有校区和名称；同 ID 会保存旧版本后更新。")
    uploaded = st.file_uploader("选择地点数据文件", type=["csv", "json", "geojson"])
    confirmed = st.checkbox("我已核对校区、来源、坐标精度和数据状态")
    if st.button("导入数据", disabled=uploaded is None or not confirmed):
        try:
            result = locations.import_data(uploaded.name, uploaded.getvalue())
            st.success(f"导入完成：新增 {result['inserted']} 条，更新 {result['updated']} 条。")
        except Exception as exc:
            st.error(f"导入失败：{exc}")

with review_tab:
    review_entries = locations.search_locations(campus=campus, include_inactive=True)
    if review_entries:
        selected_id = st.selectbox(
            "地点",
            [item.id for item in review_entries],
            format_func=lambda value: next(item.name for item in review_entries if item.id == value),
        )
        selected = next(item for item in review_entries if item.id == selected_id)
        st.json(selected.to_dict())
        verify_col, deactivate_col, rollback_col = st.columns(3)
        with verify_col:
            if st.button("标记已实地/管理员核验"):
                locations.verify_location(selected.id)
                st.success("已记录当前中国时间为核验时间。")
                st.rerun()
        with deactivate_col:
            deactivate_confirmed = st.checkbox("确认停用", key=f"deactivate-{selected.id}")
            if st.button("停用错误地点", disabled=not deactivate_confirmed):
                locations.deactivate_location(selected.id)
                st.success("已停用，历史版本仍保留。")
                st.rerun()
        with rollback_col:
            if st.button("回滚到上一版"):
                try:
                    locations.rollback_location(selected.id)
                    st.success("已回滚。")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    st.subheader("待审核纠错")
    feedback = locations.list_feedback()
    if feedback:
        st.dataframe(feedback, width="stretch", hide_index=True)
    else:
        st.info("当前没有待审核纠错。")
    st.subheader("档口管理")
    stalls = locations.list_food_stalls(campus=campus, include_inactive=True)
    if stalls:
        stall_id = st.selectbox(
            "饭堂档口",
            [item.id for item in stalls],
            format_func=lambda value: next(item.name for item in stalls if item.id == value),
        )
        stall = next(item for item in stalls if item.id == stall_id)
        st.json(stall.to_dict())
        stall_confirmed = st.checkbox("确认停用该档口", key=f"stall-confirm-{stall.id}")
        if st.button("停用错误档口", disabled=not stall_confirmed):
            locations.deactivate_food_stall(stall.id)
            st.success("已逻辑停用档口，没有直接删除历史记录。")
            st.rerun()
    else:
        st.info("当前校区没有档口记录。")

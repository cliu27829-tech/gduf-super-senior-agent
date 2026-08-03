"""三校隔离的校园地图、饭堂详情与地点纠错页。"""

from __future__ import annotations

import uuid

import pandas as pd
import streamlit as st

from core.models import CAMPUSES, LOCATION_CATEGORIES
from core.time_service import format_current_time_prompt
from services.location_service import LocationService
from ui.map_helpers import build_map_rows, filter_locations
from ui.navigation import safe_page_link


st.set_page_config(page_title="校园地图 - 广金大师兄", page_icon="🗺️", layout="wide")

if "user_id" not in st.session_state:
    st.session_state.user_id = f"session-{uuid.uuid4()}"
if "user_campus" not in st.session_state:
    st.session_state.user_campus = CAMPUSES[0]


@st.cache_resource
def get_location_service() -> LocationService:
    return LocationService()


service = get_location_service()
st.title("🗺️ 校园地图")
st.caption(format_current_time_prompt())
st.info("地图中的部分点位是校内相对示意坐标，不是可直接用于导航的 GPS 坐标。")

with st.sidebar:
    safe_page_link("app.py", "返回首页")
    campus = st.selectbox(
        "校区",
        CAMPUSES,
        index=CAMPUSES.index(st.session_state.user_campus)
        if st.session_state.user_campus in CAMPUSES
        else 0,
    )
    st.session_state.user_campus = campus
    query = st.text_input("搜索地点或别名")
    translated_categories = {
        "canteen": "饭堂",
        "food_stall": "档口",
        "teaching_building": "教学楼",
        "dormitory": "宿舍",
        "library": "图书馆",
        "medical": "医务室",
        "express_station": "快递站",
        "supermarket": "超市",
        "sports": "体育场馆",
        "campus_gate": "校门",
        "administrative_service": "行政服务",
        "campus_card_service": "校园卡服务",
        "atm": "ATM",
        "printing": "打印",
        "other": "其他",
    }
    category_labels = {
        "": "全部",
        **{value: translated_categories.get(value, value) for value in LOCATION_CATEGORIES},
    }
    category = st.selectbox(
        "分类",
        list(category_labels),
        format_func=lambda value: category_labels[value],
    )
    canteen_only = st.checkbox("只看饭堂")
    open_only = st.checkbox("只看现在营业")
    st.caption("“现在营业”只对已核验且有可解析营业时间的条目生效。")
    campus_locations = service.search_locations(campus=campus)
    nearby_enabled = st.checkbox("按已知地点查附近")
    origin_id = None
    nearby_limit = 5
    if nearby_enabled and campus_locations:
        origin_id = st.selectbox(
            "附近搜索起点",
            [item.id for item in campus_locations],
            format_func=lambda value: next(item.name for item in campus_locations if item.id == value),
        )
        nearby_limit = st.slider("最多结果", 1, 15, 5)

visible = filter_locations(
    campus_locations,
    query=query,
    category=category or None,
    canteen_only=canteen_only,
    open_only=open_only,
)
nearby_rows = []
if nearby_enabled and origin_id:
    origin = next(item for item in campus_locations if item.id == origin_id)
    nearby_rows = service.find_nearby_locations(
        campus=campus,
        latitude=origin.latitude,
        longitude=origin.longitude,
        map_x=origin.map_x,
        map_y=origin.map_y,
        category=category or ("canteen" if canteen_only else None),
        limit=nearby_limit + 1,
    )
    nearby_by_id = {
        item["location"]["id"]: item
        for item in nearby_rows
        if item["location"]["id"] != origin_id
    }
    visible = [item for item in visible if item.id in nearby_by_id]
    visible.sort(key=lambda item: nearby_by_id[item.id]["distance"])
    visible = visible[:nearby_limit]
map_rows = build_map_rows(visible)

metric_a, metric_b, metric_c = st.columns(3)
metric_a.metric("当前校区地点", len(campus_locations))
metric_b.metric("筛选结果", len(visible))
metric_c.metric("待核验/过期", sum(item.freshness_status != "current" for item in visible))
if nearby_enabled and origin_id:
    origin = next(item for item in campus_locations if item.id == origin_id)
    precision = next((item["precision"] for item in nearby_rows if item["location"]["id"] != origin_id), None)
    st.caption(
        f"已按“{origin.name}”计算附近地点；"
        + ("使用 GPS 球面距离。" if precision == "gps" else "使用校内示意坐标距离，不代表实际米数。")
    )

campus_maps = service.list_campus_maps(campus)
if campus_maps:
    map_record = campus_maps[0]
    st.subheader("管理员上传的校园底图")
    st.image(map_record["file_path"], caption=f"上传时间：{map_record['uploaded_at']}")
    st.caption("底图与下方示意点目前未做像素级叠加；点位仍以详情卡的坐标精度为准。")

gps_rows = [row for row in map_rows if row["coordinate_type"] == "gps"]
schematic_rows = [row for row in map_rows if row["coordinate_type"] == "schematic"]
if gps_rows:
    st.subheader("精确坐标地图")
    gps_frame = pd.DataFrame(gps_rows).rename(columns={"latitude": "lat", "longitude": "lon"})
    st.map(gps_frame[["lat", "lon"]])
if schematic_rows:
    st.subheader("校内相对位置示意图")
    st.caption("坐标范围 0–1，仅用于表达校内相对方位。")
    chart_frame = pd.DataFrame(schematic_rows)
    st.scatter_chart(chart_frame, x="map_x", y="map_y", color="category", size=90)
if not map_rows:
    st.warning("没有符合条件且具有坐标的地点。")

st.subheader("地点详情")
if not visible:
    st.info("没有匹配的地点，请放宽筛选条件。")
else:
    selected_id = st.selectbox(
        "选择地点",
        [item.id for item in visible],
        format_func=lambda value: next(item.name for item in visible if item.id == value),
    )
    selected = next(item for item in visible if item.id == selected_id)
    if nearby_enabled and selected.id in nearby_by_id:
        nearby_item = nearby_by_id[selected.id]
        distance_label = (
            f"{nearby_item['distance']:.0f} 米"
            if nearby_item["unit"] == "m"
            else f"{nearby_item['distance']:.3f} 示意单位"
        )
        st.info(f"与起点的距离：{distance_label}")
    left, right = st.columns([3, 2])
    with left:
        st.markdown(f"### {selected.name}")
        st.write(selected.description or "暂无描述。")
        st.write(f"**校区：**{selected.campus}")
        st.write(f"**区域/楼层：**{selected.area or selected.building or '待核验'} {selected.floor}")
        st.write(f"**营业或开放时间：**{selected.opening_hours or '待核验'}")
        st.write(f"**服务：**{'、'.join(selected.services) or '待核验'}")
        st.write(f"**支付方式：**{'、'.join(selected.payment_methods) or '待核验'}")
        st.write(f"**数据状态：**{selected.data_status} / {selected.freshness_status}")
        if selected.freshness_status != "current":
            st.warning("该条目不在新鲜度窗口内，使用前请与校方或现场信息复核。")
        st.link_button("打开导航/地图搜索", service.build_navigation_link(selected))
    with right:
        st.markdown("#### 来源与核验")
        st.write(f"**核验方式：**{selected.verification_method}")
        st.write(f"**核验时间：**{selected.verified_at or '尚未当前核验'}")
        st.write(f"**置信度：**{selected.confidence:.0%}")
        if selected.source_references:
            for source in selected.source_references:
                if source.url:
                    st.markdown(f"- [{source.title}]({source.url})（{source.source_status}）")
                else:
                    st.markdown(f"- {source.title}（{source.source_status}）")
                st.caption(
                    f"发布机构：{source.publisher or '未记录'}｜"
                    f"发布日期：{source.published_at or '未提取'}｜"
                    f"抓取时间：{source.fetched_at or '未记录'}｜"
                    f"来源等级：{source.source_level}｜"
                    f"官方：{'是' if source.is_official else '否'}"
                )
        else:
            st.caption("无可引用来源。")

    if selected.category == "canteen":
        st.subheader("饭堂与档口")
        details = service.get_canteen_details(selected.id)
        st.warning(details["today_menu_message"] if details else "目前没有可靠的饭堂数据。")
        stalls = details["food_stalls"] if details else []
        if stalls:
            st.dataframe(
                [
                    {
                        "档口": item["name"],
                        "楼层": item["floor"] or "待核验",
                        "食物类型": item["food_type"] or "待核验",
                        "价格": item["price_range"] or "待核验",
                        "营业": "待核验" if item["is_operating"] is None else ("是" if item["is_operating"] else "否"),
                        "状态": item["data_status"],
                    }
                    for item in stalls
                ],
                width="stretch",
                hide_index=True,
            )

    with st.expander("提交地点纠错"):
        feedback = st.text_area(
            "请说明错误和可核验依据",
            key=f"feedback-{selected.id}",
        )
        if st.button("提交待审核纠错", disabled=not feedback.strip()):
            feedback_id = service.submit_location_feedback(
                campus=campus,
                feedback=feedback,
                user_id=st.session_state.user_id,
                location_id=selected.id,
            )
            st.success(f"已提交，编号 {feedback_id}。不会自动改写正式地点数据。")

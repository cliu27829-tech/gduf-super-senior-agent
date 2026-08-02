# 校园地点与饭堂数据模型

## CampusLocation

| 字段 | 用途 |
|---|---|
| `id` | 稳定唯一 ID，导入时同 ID 触发更新与版本记录 |
| `name`, `aliases` | 标准名称与校内俗称 |
| `campus` | 仅允许广州校本部、肇庆校区、清远校区 |
| `category`, `sub_category` | 饭堂、教学楼、宿舍、图书馆、医务、快递等类型 |
| `description` | 不包含未验证推测的描述 |
| `building`, `floor`, `area`, `address` | 建筑、楼层、校内区域和地址 |
| `latitude`, `longitude` | 只能存放可用于地图的真实坐标 |
| `map_x`, `map_y` | 0–1 校内示意坐标，不得冒充 GPS |
| `opening_hours`, `phone` | 开放/营业时间和电话 |
| `services`, `payment_methods` | 服务项和支付方式列表 |
| `navigation_url` | 可选人工指定导航链接；否则动态生成高德链接 |
| `source_references` | 来源数组，见下文 |
| `verification_method`, `verified_at` | 核验方式与带时区时间 |
| `valid_from`, `valid_until` | 可选有效期 |
| `freshness_status` | `current`, `stale`, `expired`, `needs_verification` |
| `confidence` | 0–1 置信度 |
| `is_active` | 逻辑删除开关 |
| `data_status` | `verified`, `historical_seed`, `demo_fixture`, `needs_verification` 等数据状态 |
| `created_at`, `updated_at` | 中国时区 ISO 8601 审计时间 |

## CanteenInfo

`CanteenInfo` 表示饭堂内的档口或餐饮单元，不表示当日菜单。字段包括 `canteen_id`、饭堂所在校区、档口名、楼层、食物类型、常见餐品、价格区间、早/中/晚餐时段、营业时间、支付方式、当前营业状态、核验时间、来源、置信度、数据状态与逻辑删除开关。

`get_canteen_details()` 的 `today_menu` 在没有专用当日来源时必须为空，`today_menu_available` 必须为 `false`。

## SourceReference

- `title`, `url`, `publisher`
- `published_at`：来源发布日期，不等于抓取日期。
- `fetched_at`：最近抓取时间。
- `source_level`：1–8 来源优先级。
- `is_official`：是否为校方或校方部门公开源。
- `source_status`：`current_source`, `historical`, `unverified` 等。

## SQLite 表

| 表 | 职责 |
|---|---|
| `campus_locations` | 当前地点事实 |
| `location_versions` | 每次更新前的完整 JSON 快照，支持回滚 |
| `food_stalls` | 饭堂档口与餐饮单元 |
| `location_sources` | 官方源缓存、哈希、时间与最后错误 |
| `data_refresh_logs` | 每次来源刷新结果 |
| `user_location_feedback` | 按用户和校区记录的待审核纠错 |
| `tasks` | 按 `user_id` 隔离的任务生命周期 |

## 新鲜度默认阈值

| 数据类型 | 默认阈值 |
|---|---:|
| 当日菜单 | 1 天 |
| 当前营业状态 | 7 天 |
| 档口信息 | 30 天 |
| 营业时间 | 90 天 |
| 固定地点 | 180 天 |

阈值可在创建 `LocationService` 时覆盖。没有 `verified_at` 的条目无论年份多新都是 `needs_verification`。

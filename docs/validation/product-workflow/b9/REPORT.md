# B9 · 闲鱼发布页类目/虚拟商品要求核验（只读）

> 任务：`task-5218b4db31ec7495b1bd24f5bdbab7a8`（revision 2，计划 v7）；执行者 session-01ba487c…。
> 范围：`docs/validation/product-workflow/b9`；只读使用 `tools/platform-login/profile` 闲鱼 profile；未登录新账号、未扫码、未填写/提交发布表单、未采购/私信/发布。
> 采样：2026-10-23 21:08–21:12 UTC+8（13:08–13:12Z）；截图见 `shots/`，原文/HTML 见 `raw/`，命令与真实 exit 见 `logs/`。

## 0. 结论（四选一）

**证据不足**：当前 profile 的页面显示**未登录**（首页右上角“登录”；`/publish` 弹出短信/扫码登录框），因此没有进入类目选择页，未取得“文档/电子/虚拟/资料”类目结构与该类目发布要求。

- 不能判定“可发布”：没看到类目/要求；
- 不能判定“不可发布”：没有看到禁止性提示；
- 不能判定“需资质”：没有看到类目内资质/保证金/授权提示；
- 缺的是：**有效登录态 + 发布页类目选择 + 类目细则/提示**（见 §4–§5）。

## 1. login：profile 有 `unb` 名称，但页面未登录

- Profile：`D:\桌面\two\tools\platform-login\profile`（已有，未复制/未改）；浏览器从该 profile 启动。
- CDP 仅读 cookie **名称**：22 个名称，包含 `unb`（`raw/login_metadata.json`；**未读取/打印任何 cookie 值**）。
- 首页 `https://www.goofish.com/`：title `闲鱼 - 闲不住？上闲鱼！`；正文头部有 **“登录 / 订单 / 消息”**，`home_has_login_button=true`。截图 [01_home.jpg](shots/01_home.jpg)。
- 发布入口 `https://www.goofish.com/publish`：title `发闲置_闲鱼`，正文为：
  - `登录`
  - `订单`
  - `消息`
  - `APP`
  - `反馈`
  - `客服`
  - `回顶部`
  - `登录后可以更懂你，推荐你喜欢的商品！`
  - `立即登录`
- 页面出现短信登录/手机扫码安全登录框（截图 [02_publish.jpg](shots/02_publish.jpg)）。**页面是登录态最终判据：未登录**；仅有 `unb` 名称不表示服务端会话有效。
- 未点击登录框内任何按钮/未扫码/未输入手机号/验证码；脚本检测到“立即登录/登录后可以”即停止。

## 2. categories：未见类目结构（不是“不存在”）

- `/publish` 被登录框覆盖，未出现“选择类目/选择分类”入口；`03_category` 仍为同一登录页。
- 自动收集的页面候选中只有页脚“电子营业执照”等文本：
  - `电子营业执照` 是页脚/证照链接，**不是商品类目**；
  - 未见“文档/电子/虚拟/资料/其他”类目入口或层级。
- 因此只能记录：**本次会话未见类目结构**；不能推断平台“不存在”该类目，也未取得类目名、必填项、层级。
- 原始页面：`raw/02_publish.html`、`raw/02_publish.txt`；候选：`raw/02_publish_candidates.json`；截图 [02_publish.jpg](shots/02_publish.jpg)。

## 3. requirements：未取得资质/保证金/特殊类目提示

- 登录框后没有进入发布表单，因此**未取得**任何“需要资质/保证金/特殊类目授权”的类目内提示。
- 未看到“电子出版物/出版物经营许可证”在本商品类目下的具体提示；B8 摘录的官方规范 L167–170 仍只能作为通用规则，不能替代类目细则。
- 不对 Excel 模板的类目归属或资质要求作外推。

## 4. 移动端尝试（m.goofish.com）

- 浏览器访问 `https://m.goofish.com/publish`：Chrome `ERR_CONNECTION_CLOSED`，title `m.goofish.com`；截图 [mobile_02_publish.jpg](shots/mobile_02_publish.jpg)；日志 `logs/probe_mobile_run.log`。
- `curl` 直接访问：exit **6**（`Could not resolve host: m.goofish.com`）；经代理：exit **35**（SSL/TLS handshake failed）；日志 `logs/mobile_direct_curl.log`、`logs/mobile_proxy_curl.log`。
- 结论：移动端页面未取得；不作为类目证据。

## 5. 四选一依据与缺口

| 结论 | 是否成立 | 依据 |
| --- | --- | --- |
| 可发布 | 否 | 未看到类目/要求；登录墙阻断 |
| 不可发布 | 否 | 未看到“禁止电子表格/虚拟商品”等禁止性提示 |
| 需资质 | 否 | 未进入类目，未看到资质/保证金提示 |
| **证据不足** | **是** | 未登录；未取得类目选择页与类目要求；移动端不可达 |

**缺什么**：

1. 有效的闲鱼登录态（当前 profile 页面显示未登录；不新建登录/不扫码）；
2. 登录后可进入的发布页“选择类目”及“文档/电子/虚拟/资料/其他”实际层级；
3. 该类目的必填项、资质/保证金/授权提示、电子出版物资质是否适用；
4. 至少 2 张类目相关截图（当前只有首页 + 登录墙截图，非类目页）。

## 6. 证据

| 证据 | 路径 |
| --- | --- |
| 首页截图（登录按钮） | [01_home.jpg](shots/01_home.jpg) |
| 发布入口截图（登录框） | [02_publish.jpg](shots/02_publish.jpg) |
| 首页文本/HTML | `raw/01_home.txt`、`raw/01_home.html` |
| 发布页文本/HTML | `raw/02_publish.txt`、`raw/02_publish.html` |
| 登录态元数据（仅名称） | `raw/login_metadata.json` |
| 最终探测结果 | `raw/probe_result.json` |
| 移动端错误 | `raw/mobile_02_publish.txt`、`shots/mobile_02_publish.jpg` |
| 真实命令/exit | `logs/probe_publish_run3.log`（exit=2）、`logs/probe_publish.log`、`logs/probe_mobile_run.log`、`logs/mobile_direct_curl.log`（6）、`logs/mobile_proxy_curl.log`（35） |

- 页面 HTML 已去除 script/style 并对 input/token 值做占位；报告不包含 cookie/token 值，只记录 `unb` 等名称/数量。
- 截图由 nodriver 实际保存为 JPEG 字节，已按真实格式改名为 `.jpg`；未伪造/未用示意图。

## 7. 限制与下一步

1. **未登录**：profile 中 `unb` 名称存在但页面未登录（短信/扫码框）；未做任何登录动作，未索取验证码。
2. **未取得类目**：登录墙阻断；不能把“页脚电子营业执照”当类目，也不能说平台不存在该类别。
3. **未取得资质提示**：没有进入类目表单；B8 的电子出版物资质条款是否适用于 Excel 仍未核验。
4. 移动端 `m.goofish.com` DNS/TLS/连接失败（exit 6/35/ERR_CONNECTION_CLOSED）；未绕过。
5. 全程只读：未填写标题/价格/图片，未点发布/提交/保存，未私信/加购/改资料，未采购/发布。
6. 若用户希望继续，需要**用户本人**在可见窗口重新建立该 profile 的闲鱼登录态，然后另批复核类目；本轮不自行扫码/登录。

## 8. 与 B8 / C3 的关系

- [B8 PLATFORM-RULES.md](../b8/PLATFORM-RULES.md) 的官方规范摘录仍有效，但“电子表格类目 + 电子出版物资质”仍**未核验**；本报告不把 B8 的通用规则升级为类目结论。
- C3 学习计划 Excel 的“能否发布/归哪个类目/是否需资质”**保持未决**；在取得有效登录态与类目页前，不应上架或对外承诺。

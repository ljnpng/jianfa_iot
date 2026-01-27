# Home Assistant 海信智能设备组件

这是一个用于控制海信智能设备的 Home Assistant 自定义组件。

## 功能特点

- 支持通过 HTTP API 控制海信智能设备
- 支持灯光控制
- 支持空调控制
- 支持中英文界面
- 支持状态同步和缓存
- 完整的错误处理
- 自动重试机制

## 支持的设备类型

1. 智能灯

   - 开/关控制
   - 状态显示

2. 空调设备
   - 开/关控制
   - 模式切换（制冷/制热/除湿/送风）
   - 温度控制（16-30°C）
   - 温度显示
   - 风速控制（自动/低速/中速/高速）
   - 状态同步

## 技术特性

1. 状态管理

   - 实时状态同步
   - 状态缓存机制
   - 状态变化通知

2. 错误处理

   - 自定义异常类型
   - 详细的错误信息
   - 自动重试机制

3. 网络优化

   - HTTP 请求缓存
   - 请求合并
   - 连接重试

4. 代码质量
   - 完整的单元测试
   - 类型注解
   - 详细的代码注释

## 安装说明

### 前提条件

1. 已经安装并运行了 Home Assistant
2. 有权限访问 Home Assistant 的配置目录
3. 知道设备的基本信息（设备 ID、设备名称等）

### 手动安装步骤

1. 找到 Home Assistant 配置目录

   - 如果是 Docker 安装，通常是容器内的 `/config` 目录
   - 如果是直接安装，通常在 `~/.homeassistant/` 或 `/home/homeassistant/.homeassistant/`

2. 创建自定义组件目录（如果不存在）：

   ```bash
   mkdir -p /path/to/homeassistant/config/custom_components/jianfa_iot
   ```

3. 复制组件文件到自定义组件目录：

   ```bash
   # 假设你已经下载了组件文件
   cp -r * /path/to/homeassistant/config/custom_components/jianfa_iot/
   ```

4. 设置正确的文件权限：

   ```bash
   sudo chown -R homeassistant:homeassistant /path/to/homeassistant/config/custom_components/jianfa_iot
   sudo chmod -R 755 /path/to/homeassistant/config/custom_components/jianfa_iot
   ```

5. 重启 Home Assistant：
   - 如果是 Docker 安装：
     ```bash
     docker restart homeassistant
     ```
   - 如果是直接安装，可以在 Home Assistant 界面中重启

## 配置说明

### 设备信息获取

在配置组件前，你需要准备以下信息：

1. 设备 ID：

   - 灯设备格式：`a005096001842712fffe91cac7-FirstPower`
   - 空调设备格式：`a005123001010112fffe91d203-connector.device.type.aircondition`
   - 位置：设备的唯一标识符，可以从设备信息中获取

2. 设备名称：
   - 格式示例：`客厅主灯`、`客厅空调`
   - 说明：设备的显示名称，可以自定义

#### 设备列表

- 客厅主灯
  - 名称：客厅主灯
  - id：a005096001842712fffe91cac7-FirstPower
- 客餐灯带
  - 名称：客餐灯带
  - id：a005096001842712fffe91cac7-SecondPower
- 餐厅主灯
  - 名称：餐厅主灯
  - id：a005096001842712fffe91cac7-ThirdPower
- 过道筒灯
  - 名称：过道筒灯
  - id：a005096001842712fffe91cac7-FourthPower
- 客厅空调
  - 名称：客厅空调
  - id：a005123001010112fffe91d203-connector.device.type.aircondition

### 基本配置

1. 在 Home Assistant 的 Web 界面中：

   - 转到"配置" -> "集成"
   - 点击右下角的"添加集成"按钮
   - 搜索"海信智能设备"
   - 按照提示输入设备信息

2. 配置项说明：

   - 设备 ID（必填）：设备的唯一标识符
   - 设备名称（必填）：设备的显示名称
   - 名称（可选）：在 Home Assistant 中显示的名称，默认使用设备名称

3. 设备类型说明：
   - 系统会根据设备 ID 自动识别设备类型
   - 空调设备会显示为 climate 实体
   - 灯设备会显示为 light 实体

### 空调设备使用说明

1. 基本控制：

   - 开/关：可以通过 Home Assistant 的开关按钮控制
   - 模式：支持多种运行模式
     - 制冷：制冷模式
     - 制热：制热模式
     - 除湿：除湿模式
     - 送风：仅送风模式
     - 关闭：关闭空调
   - 温度控制：可以设置 16-30°C 之间的温度
   - 温度显示：显示当前设定温度
   - 风速控制：支持自动、低速、中速、高速

2. 状态同步：

   - 支持实时状态同步
   - 状态缓存减少请求次数
   - 自动重试确保命令执行

3. 注意事项：

   - 支持基本的开关控制
   - 支持温度调节功能
   - 支持完整的模式切换
   - 支持风速调节
   - 支持状态同步

4. 使用建议：
   - 开机时如果没有指定模式，默认会进入制冷模式
   - 切换模式时如果设备是关闭状态，会自动开机
   - 建议根据季节选择合适的运行模式
   - 使用自动风速可以让设备自动调节风速

### 认证信息

组件现在支持短信验证码登录并自动保存 token：

- 初次添加集成时，会引导输入手机号并请求验证码；输入验证码后完成登录并发现设备。
- 运行中如果 token 过期：
  - 可调用服务 `jianfa_iot.request_sms_code` 发送验证码到保存的手机号；
  - 再调用 `jianfa_iot.login_with_code` 传入 `code`（可选传 `phone`）完成登录并自动更新 X-token；
  - 或直接调用 `jianfa_iot.set_access_token` 手工更新 `access_token`。

示例（开发者工具 -> 服务）：

1. 发送验证码：
```
service: jianfa_iot.request_sms_code
data: {}
```

2. 使用验证码登录：
```
service: jianfa_iot.login_with_code
data:
  code: "274813"
```

3. 直接设置 token：
```
service: jianfa_iot.set_access_token
data:
  access_token: "<your token>"
```

## 故障排除

### 常见问题

1. 组件没有出现在集成列表中：

   - 检查组件文件是否正确复制到 custom_components 目录
   - 检查文件权限是否正确（755）
   - 检查 Home Assistant 日志中是否有错误信息
   - 确保已经重启了 Home Assistant

2. 无法控制设备：

   - 确认设备 ID 是否正确
   - 检查网络连接是否正常
   - 查看 Home Assistant 日志中的详细错误信息
   - 验证认证信息是否正确
   - 检查设备是否在线

3. 空调设备特定问题：

   - 如果无法切换模式，检查设备 ID 是否正确
   - 如果无法调节温度，确保温度设置在 16-30°C 范围内
   - 如果模式切换后没有反应，尝试先关闭再重新打开设备
   - 如果状态不同步，等待几秒钟后重试

4. 网络问题：

   - 如果出现网络错误，组件会自动重试
   - 如果持续失败，检查网络连接
   - 查看错误日志了解具体原因

5. 状态同步问题：
   - 如果状态不准确，可以手动刷新
   - 检查设备是否在线
   - 确认网络连接正常

### 日志查看

要查看组件的日志信息：

1. 在 Home Assistant 的配置文件 `configuration.yaml` 中添加：

   ```yaml
   logger:
     default: info
     logs:
       custom_components.jianfa_iot: debug
   ```

2. 重启 Home Assistant 后查看日志

3. 日志级别说明：
   - DEBUG：详细的调试信息
   - INFO：一般操作信息
   - WARNING：警告信息
   - ERROR：错误信息

## 开发说明

### 代码结构

```
custom_components/jianfa_iot/
├── __init__.py           # 组件初始化
├── climate.py            # 空调设备实现
├── light.py             # 灯设备实现
├── const.py             # 常量定义
├── config_flow.py       # 配置流程
├── http_client.py       # HTTP 客户端
├── state_manager.py     # 状态管理器
├── exceptions.py        # 异常定义
├── manifest.json        # 组件清单
├── translations/        # 翻译文件
└── tests/              # 测试文件
    ├── __init__.py
    └── test_climate.py
```

### 开发环境设置

1. 安装依赖：

   ```bash
   pip install homeassistant
   pip install pytest
   pip install pytest-asyncio
   ```

2. 运行测试：
   ```bash
   pytest custom_components/jianfa_iot/tests/
   ```

### 代码贡献

1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 创建 Pull Request

## 支持与反馈

如果您遇到问题：

1. 检查 Home Assistant 的日志文件
2. 提交 Issue 到本仓库
3. 提供以下信息：
   - Home Assistant 版本
   - 组件版本
   - 错误日志
   - 复现步骤

## 更新日志

### v1.1.0

- 添加状态管理器
- 实现状态同步
- 添加错误处理
- 优化网络请求
- 添加单元测试

### v1.0.0

- 初始版本
- 基本功能实现
- 支持空调和灯设备

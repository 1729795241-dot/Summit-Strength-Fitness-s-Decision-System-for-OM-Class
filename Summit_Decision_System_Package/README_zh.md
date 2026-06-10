# Summit 库存审查工具

## 一键启动

双击：

`start_frontend.bat`

启动后会自动打开浏览器。如果浏览器没有自动打开，请在终端里复制显示的本地地址，例如：

`http://127.0.0.1:8765/`

## 使用流程

1. 在页面顶部输入 `DEEPSEEK_API_KEY`。
2. 点击 `Run Review`。
3. 系统会先跑库存模型，再调用 `deepseek-v4-pro` 做一次结果审查。
4. 页面会展示：
   - Review Summary
   - KPI Summary
   - Lateral Transfers
   - Production Signals

## API key 说明

前端输入的 key 只在本次请求中传给本地后端，不会写入文件。

如果希望从命令行运行，也可以自己新建 `.env` 文件：

```text
DEEPSEEK_API_KEY=your_key_here
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

如果没有 key，页面仍可读取已有结果；只有重新运行审查时才需要 key。

## 主要文件

- `app.py`: 本地页面和接口服务
- `summit_inventory_system.py`: 决策系统核心模型
- `static/`: 前端页面
- `data/`: CSV/JSON 输出
- `reports/simulation_data_and_system_results.md`: 系统结果报告

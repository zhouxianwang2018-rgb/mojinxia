# 常见故障排查

> v1.1 · 2026-06-04

## 引擎一输出为空

**现象**：引擎一扫描执行成功但 `candidate_pool.engine1` 为空对象 `{}`。

**原因**：
1. `early_breakout_scanner.py` 参数错误
2. 腾讯 K 线 API 返回异常
3. 当日无可触发 STAGE2/STAGE3 的标的

**排查**：
```bash
# 手动运行脚本看输出
python3 ~/.hermes/scripts/early_breakout_scanner.py 2>&1 | head -30

# 检查策略文件中 engine1 字段
cat ~/.hermes/cron/state/moni/strategies/$(date +%Y-%m-%d).json | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d['current_strategy']['candidate_pool']['engine1'], indent=2))"
```

## 引擎二板块集中度查询失败

**现象**：`engine2_ranker.py` 报错 "查数据出错，无数据返回"。

**原因**：妙想 MCP API 鉴权方式已从 `apikey: <key>` 变更为 `Authorization: Bearer <key>`，且 searchData 接口参数格式可能已变。

**对策**：
1. 确认 `EM_API_KEY` 是最新的
2. 引擎二当前仍可用但不稳定，关注迭代计划中的 SRS-002 修复

## CRON Broken pipe

**现象**：cron 报 `RuntimeError: [Errno 32] Broken pipe`。

**原因**：DeepSeek 流式连接在高负载时断开（180s 超时无数据）。

**对策**：自动重试。通常第二次能成功。若连续失败 3 次，手动触发：
```bash
hermes cron run <job_id>
```

## 报纸图片不生成

**现象**：盘前定调/收盘复盘只输出文字，无图片。

**排查**：
```bash
# 1. 确认 snap chromium 可用
/snap/chromium/current/usr/lib/chromium-browser/chrome --version

# 2. 手动测试图片生成
echo "## test" | python3 ~/.hermes/scripts/premarket_image.py

# 3. 若报 chromium 未找到，检查 snap
sudo snap install chromium
```

## 妙想 API 返回 401

**现象**：妙想 MCP 接口返回 401 Unauthorized。

**原因**：鉴权方式变更。旧方式（header `apikey`）已废弃。

**对策**：确认使用 `Authorization: Bearer <EM_API_KEY>` header。

## 腾讯 K 线数据异常

**现象**：K 线 API 返回空或异常数据。

**排查**：
```bash
# 手动测试
curl -s "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh688082,day,,,3,qfq" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('data',{}).get('sh688082',{}).get('qfqday',[])))"
```

**注意**：
- key 必须是 `qfqday`（前复权），不是 `day`
- volume 是字符串，需 `int(float(x))`
- 上海 `sh` 前缀，深圳 `sz` 前缀
- Eastmoney push2 已屏蔽，不可用

## 策略文件被并发写入破坏

**现象**：策略文件 JSON 损坏或字段丢失。

**原因**：两个 cron 同时写入同一策略文件。

**对策**：
1. 确认各 cron 时间间隔 >= 3 分钟（当前间隔足够）
2. 如果出现，手动从备份恢复：
```bash
cp ~/.hermes/cron/state/moni/strategies/$(date +%Y-%m-%d).json.bak \
   ~/.hermes/cron/state/moni/strategies/$(date +%Y-%m-%d).json
```

## Cron 执行了但 QQ 没收到消息

**排查**：
```bash
# 1. 检查交付日志
grep "delivered to qqbot" ~/.hermes/logs/agent.log | grep $(date +%Y-%m-%d)

# 2. 检查 QQ Bot WebSocket
grep "QQBot.*WebSocket" ~/.hermes/logs/gateway.log | tail -5

# 3. 检查 cron 输出文件
ls -lt ~/.hermes/cron/output/<job_id>/
```

若 delivery log 显示成功但用户未收到，通常是 QQ Bot WebSocket 短暂断连，自动重连后恢复正常。

import requests
import time

# 🚀 扩展区：把你想监控的币种全填在这里
WATCH_LIST = ["WIF", "SOL", "PEPE", "BOME", "BTC"]
THRESHOLD = 0.5  # 统一的波动报警阈值（%）

# 状态字典：在内存中持久化记录所有币种的“上一秒基准价”
last_prices = {symbol: 0.0 for symbol in WATCH_LIST}

def get_all_market_data():
    """架构升级：一次 HTTP 请求，拉取全市场快照，本地组装 Hash Map"""
    # 注意：去掉了末尾的 ?symbol=...
    url = f"http://{GCP_IP}/mexc/api/v3/ticker/price"
    
    try:
        res = requests.get(url, timeout=8)
        if res.status_code != 200:
            print(f"⚠️ 网关抖动: {res.status_code}")
            return None
            
        data = res.json()
        
        # 将 [{"symbol":"BTCUSDT", "price":"60000"}, ...] 的数组
        # 转换为 {"BTCUSDT": 60000.0, ...} 的字典，实现 O(1) 本地极速查询
        price_map = {}
        for item in data:
            price_map[item['symbol']] = float(item['price'])
            
        return price_map
        
    except Exception as e:
        print(f"💥 快照拉取异常: {e}")
        return None

def ask_gemini(symbol, price, change):
    """动态组装 Prompt，支持多币种独立分析"""
    url = f"http://{GCP_IP}/gemini/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    prompt_text = f"你是经验丰富的 Web3 交易员。${symbol} 当前价格 ${price}，近期波动 {change:.2f}%。用极具嘲讽或热血的网感语境写一句点评，带 Emoji，50 字内。"
    payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
    
    try:
        res = requests.post(url, json=payload, timeout=15).json()
        return res['candidates'][0]['content']['parts'][0]['text']
    except Exception:
        return "🤖 AI 正在疯狂计算中，暂时无法输出骚话..."

def send_tg(text):
    """推送逻辑不变"""
    url = f"http://{GCP_IP}/tg/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

# === 多线程/并发监控大循环 ===
print(f"🚀 矩阵监控启动！当前监听序列: {WATCH_LIST}")

while True:
    print(f"[{time.strftime('%H:%M:%S')}] 📡 正在拉取全市场行情快照...")
    
    # 1. 发起一次网络请求，拿到几千个币的价格
    market_snapshot = get_all_market_data()
    
    if market_snapshot:
        # 2. 遍历我们的监控名单，在内存里进行极速比对
        for symbol in WATCH_LIST:
            pair_name = f"{symbol}USDT"
            current_price = market_snapshot.get(pair_name)
            
            if current_price:
                prev_price = last_prices[symbol]
                
                # 如果是第一次拿到这个币的价格，先初始化基准线
                if prev_price == 0.0:
                    last_prices[symbol] = current_price
                    print(f"✅ {symbol} 初始价格锁定: ${current_price}")
                    continue
                
                # 计算涨跌幅
                change = ((current_price - prev_price) / prev_price) * 100
                
                # 触发报警判定
                if abs(change) >= THRESHOLD:
                    print(f"🚨 [异动] {symbol} 波动达 {change:.2f}%，唤醒 AI...")
                    
                    ai_comment = ask_gemini(symbol, current_price, change)
                    msg = f"🔔 **{symbol} 异动警报**\n\n💰 现价: ${current_price}\n📈 波动: {change:.2f}%\n\n{ai_comment}"
                    send_tg(msg)
                    
                    # 更新基准价，防止同一波段连环狂发
                    last_prices[symbol] = current_price
                else:
                    # 动态展示各个币种的微小波动
                    print(f"😴 {symbol}: ${current_price} (波动: {change:.2f}%)")
            else:
                print(f"⚠️ 交易所未找到交易对: {pair_name}")
                
    time.sleep(30)  # 休息 30 秒，准备下一轮快照

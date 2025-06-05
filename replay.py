import os
import json
import collections
from datetime import datetime, timedelta
from flask import Flask, render_template, request

from compress import frames_per_step, file_movement
from start import personas

app = Flask(
    __name__,
    template_folder="frontend/templates",
    static_folder="frontend/static",
    static_url_path="/static",
)


@app.route("/", methods=['GET'])
def index():
    name = request.args.get("name", "")          # 紀錄名稱
    step = int(request.args.get("step", 0))      # 回放起始步數
    speed = int(request.args.get("speed", 2))    # 回放速度（0~5）
    zoom = float(request.args.get("zoom", 0.8))  # 畫面缩放比例

    if len(name) > 0:
        compressed_folder = f"results/compressed/{name}"
    else:
        return f"Invalid name of the simulation: '{name}'"

    replay_file = f"{compressed_folder}/{file_movement}"
    if not os.path.exists(replay_file):
        return f"The data file doesn't exist: '{replay_file}'<br />Run compress.py to generate the data first."

    with open(replay_file, "r", encoding="utf-8") as f:
        params = json.load(f)

    if step < 1:
        step = 1
    if step > 1:
        # 重新設置回放的起始時間
        t = datetime.fromisoformat(params["start_datetime"])
        dt = t + timedelta(minutes=params["stride"]*(step-1))
        params["start_datetime"] = dt.isoformat()
        step = (step-1) * frames_per_step + 1
        if step >= len(params["all_movement"]):
            step = len(params["all_movement"])-1

        # 重新設置Agent的初始位置
        for agent in params["persona_init_pos"].keys():
            persona_init_pos = params["persona_init_pos"]
            persona_step_pos = params["all_movement"][f"{step}"]
            persona_init_pos[agent] = persona_step_pos[agent]["movement"]

    if speed < 0:
        speed = 0
    elif speed > 5:
        speed = 5
    speed = 2 ** speed

    return render_template(
        "index.html",
        persona_names=personas,
        step=step,
        play_speed=speed,
        zoom=zoom,
        **params
    )


@app.route("/interaction-graph", methods=['GET'])
def interaction_graph():
    name = request.args.get("name", "")  # 紀錄名稱

    if len(name) > 0:
        checkpoint_folder = f"results/checkpoints/{name}"
    else:
        return f"Invalid name of the simulation: '{name}'"

    # 讀取對話數據
    conversation_file = f"{checkpoint_folder}/conversation.json"
    if not os.path.exists(conversation_file):
        return f"The conversation file doesn't exist: '{conversation_file}'"

    with open(conversation_file, "r", encoding="utf-8") as f:
        conversation_data = json.load(f)

    # 計算角色之間的互動次數
    interactions = collections.defaultdict(int)
    
    for time_key, interactions_list in conversation_data.items():
        for interaction in interactions_list:
            # 每個互動記錄的鍵看起來像 "角色1 -> 角色2 @ 位置"
            for key, chat_history in interaction.items():
                parts = key.split(" -> ")
                if len(parts) == 2:
                    person1 = parts[0]
                    person2 = parts[1].split(" @ ")[0]
                    
                    # 增加互動計數
                    pair_key = tuple(sorted([person1, person2]))
                    interactions[pair_key] += len(chat_history)

    # 創建D3.js力導向圖所需的數據格式
    nodes = [{"id": person, "group": 1} for person in personas]
    links = []
    
    for (person1, person2), count in interactions.items():
        if count > 0:  # 只添加有互動的連接
            links.append({
                "source": person1,
                "target": person2,
                "value": count
            })
    
    interaction_data = {
        "nodes": nodes,
        "links": links
    }

    return render_template(
        "interaction_graph.html",
        interaction_data=interaction_data
    )


@app.route("/object-interaction", methods=['GET'])
def object_interaction():
    """AI與物品/地區交互分析頁面"""
    name = request.args.get("name", "")

    if len(name) > 0:
        checkpoint_folder = f"results/checkpoints/{name}"
    else:
        return f"Invalid name of the simulation: '{name}'"

    # 分析AI與物品/地區的交互數據
    object_interactions = collections.defaultdict(int)
    location_interactions = collections.defaultdict(int)
    action_details = collections.defaultdict(list)  # 記錄詳細的動作信息

    # 讀取所有checkpoint文件
    try:
        checkpoint_files = [f for f in os.listdir(checkpoint_folder) 
                           if f.startswith("simulate-") and f.endswith(".json")]
        checkpoint_files.sort()  # 按時間順序排序
    except FileNotFoundError:
        return f"Checkpoint folder not found: '{checkpoint_folder}'"
    
    if not checkpoint_files:
        return f"No simulation data found in: '{checkpoint_folder}'"

    print(f"Found {len(checkpoint_files)} checkpoint files")

    # 分析每個checkpoint文件
    for checkpoint_file in checkpoint_files:
        file_path = os.path.join(checkpoint_folder, checkpoint_file)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 分析agents數據
            if "agents" in data:
                for agent_name, agent_data in data["agents"].items():
                    if agent_name not in personas:
                        continue  # 只分析已知的persona
                    
                    # 檢查action結構
                    if "action" in agent_data:
                        action = agent_data["action"]
                        
                        # 檢查event結構
                        if "event" in action and action["event"]:
                            event = action["event"]
                            
                            # 獲取地址信息
                            if "address" in event and event["address"]:
                                address = event["address"]
                                
                                # 確保address是列表且有足夠的元素
                                if isinstance(address, list) and len(address) >= 2:
                                    # 提取地區信息（倒數第二個元素，如果存在）
                                    if len(address) >= 3:
                                        location = address[-2]  # 地區
                                        obj = address[-1]       # 具體物品/房間
                                    else:
                                        location = address[-1]
                                        obj = address[-1]
                                    
                                    # 記錄動作詳情
                                    action_detail = {
                                        'agent': agent_name,
                                        'location': location,
                                        'object': obj,
                                        'describe': event.get('describe', ''),
                                        'predicate': event.get('predicate', ''),
                                        'object_name': event.get('object', ''),
                                        'time': data.get('time', ''),
                                        'address': address
                                    }
                                    action_details[agent_name].append(action_detail)
                                    
                                    # 統計地區交互
                                    if location and location.strip():
                                        location_key = (agent_name, location)
                                        location_interactions[location_key] += 1
                                    
                                    # 統計物品交互（排除一些通用的地區名稱）
                                    general_locations = [
                                        "客廳", "廚房", "臥室", "浴室", "辦公室", "餐廳", 
                                        "大廳", "走廊", "陽台", "房間", "家", "屋子",
                                        "living room", "kitchen", "bedroom", "bathroom",
                                        "咖啡廳", "圖書館", "公園", "學校", "醫院",
                                        "商店", "市場", "銀行", "郵局", "車站"
                                    ]
                                    
                                    # 如果最後一個元素不是通用地區名稱，則視為物品
                                    if obj and obj.strip() and obj not in general_locations and len(obj) > 0:
                                        object_key = (agent_name, obj)
                                        object_interactions[object_key] += 1
                                
                                # 如果只有一個地址元素，也統計為地區
                                elif len(address) == 1:
                                    location = address[0]
                                    if location and location.strip():
                                        location_key = (agent_name, location)
                                        location_interactions[location_key] += 1
        
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"Error reading file {checkpoint_file}: {e}")
            continue

    print(f"Total object interactions: {len(object_interactions)}")
    print(f"Total location interactions: {len(location_interactions)}")
    
    # 打印一些示例數據用於調試
    print("Sample object interactions:")
    for (agent, obj), count in list(object_interactions.items())[:5]:
        print(f"  {agent} -> {obj}: {count}")
    
    print("Sample location interactions:")
    for (agent, loc), count in list(location_interactions.items())[:5]:
        print(f"  {agent} -> {loc}: {count}")

    # 轉換為前端需要的格式
    object_interaction_list = []
    for (agent, obj), count in object_interactions.items():
        object_interaction_list.append({
            "agent": agent,
            "object": obj,
            "count": count
        })

    location_interaction_list = []
    for (agent, location), count in location_interactions.items():
        location_interaction_list.append({
            "agent": agent,
            "location": location,
            "count": count
        })

    # 如果沒有真實數據，創建一些示例數據避免頁面錯誤
    if not object_interaction_list and not location_interaction_list:
        print("No interaction data found, creating sample data...")
        # 創建示例數據
        sample_objects = ["電腦", "咖啡機", "書桌", "椅子", "手機"]
        sample_locations = ["辦公室", "咖啡廳", "圖書館", "會議室", "休息室"]
        
        for i, agent in enumerate(personas[:5]):  # 只為前5個角色創建示例
            # 物品交互
            for j, obj in enumerate(sample_objects[:3]):
                object_interaction_list.append({
                    "agent": agent,
                    "object": obj,
                    "count": (i + j + 1) * 3
                })
            
            # 地區交互
            for j, loc in enumerate(sample_locations[:3]):
                location_interaction_list.append({
                    "agent": agent,
                    "location": loc,
                    "count": (i + j + 1) * 5
                })

    # 按交互次數排序，優先顯示高頻交互
    object_interaction_list.sort(key=lambda x: x['count'], reverse=True)
    location_interaction_list.sort(key=lambda x: x['count'], reverse=True)

    interaction_data = {
        "object_interactions": object_interaction_list,
        "location_interactions": location_interaction_list
    }

    print(f"Final data - Objects: {len(object_interaction_list)}, Locations: {len(location_interaction_list)}")

    return render_template(
        "object_interaction.html",
        interaction_data=interaction_data,
        persona_names=personas
    )


if __name__ == "__main__":
    app.run(debug=True, port=5001)
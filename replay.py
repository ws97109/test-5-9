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

    # 計算角色之間的互動次數和對話長度
    interaction_count = collections.defaultdict(int)  # 互動次數
    chat_length = collections.defaultdict(int)        # 對話總長度
    
    print(f"Processing conversation data for {len(conversation_data)} time periods...")
    
    for time_key, interactions_list in conversation_data.items():
        print(f"Processing time: {time_key}, interactions: {len(interactions_list)}")
        
        for interaction in interactions_list:
            # 每個互動記錄的結構: {"角色1 -> 角色2 @ 位置": [("角色1", "對話內容"), ("角色2", "對話內容"), ...]}
            for conversation_key, chat_history in interaction.items():
                try:
                    # 解析對話鍵值，格式: "角色1 -> 角色2 @ 位置"
                    if " -> " in conversation_key and " @ " in conversation_key:
                        # 提取角色名稱
                        participants_part = conversation_key.split(" @ ")[0]  # "角色1 -> 角色2"
                        parts = participants_part.split(" -> ")
                        
                        if len(parts) == 2:
                            person1 = parts[0].strip()
                            person2 = parts[1].strip()
                            
                            # 確保角色在已知角色列表中
                            if person1 in personas and person2 in personas:
                                # 創建統一的鍵值對（按字母順序排序，避免重複）
                                pair_key = tuple(sorted([person1, person2]))
                                
                                # 統計互動次數（每次對話算一次互動）
                                interaction_count[pair_key] += 1
                                
                                # 統計對話長度（所有對話內容的字符總數）
                                if isinstance(chat_history, list):
                                    for speaker, message in chat_history:
                                        if isinstance(message, str):
                                            chat_length[pair_key] += len(message)
                                            
                                print(f"  Found interaction: {person1} <-> {person2}, messages: {len(chat_history)}")
                            else:
                                print(f"  Skipping unknown personas: {person1}, {person2}")
                        else:
                            print(f"  Invalid conversation key format: {conversation_key}")
                    else:
                        print(f"  Skipping malformed key: {conversation_key}")
                        
                except Exception as e:
                    print(f"  Error processing conversation key '{conversation_key}': {e}")
                    continue

    print(f"Total unique interactions found: {len(interaction_count)}")
    print("Interaction summary:")
    for (p1, p2), count in interaction_count.items():
        length = chat_length[(p1, p2)]
        print(f"  {p1} <-> {p2}: {count} interactions, {length} characters")

    # 創建D3.js力導向圖所需的數據格式
    nodes = []
    for i, person in enumerate(personas):
        nodes.append({
            "id": person,
            "group": (i % 3) + 1  # 分成3個組，用於不同顏色
        })

    # 創建連接數據（基於互動次數）
    interaction_links = []
    for (person1, person2), count in interaction_count.items():
        if count > 0:  # 只添加有互動的連接
            interaction_links.append({
                "source": person1,
                "target": person2,
                "value": count  # 互動次數
            })

    # 創建連接數據（基於對話長度）
    chat_length_links = []
    for (person1, person2), length in chat_length.items():
        if length > 0:  # 只添加有對話的連接
            chat_length_links.append({
                "source": person1,
                "target": person2,
                "length": length  # 對話總長度
            })

    # 如果沒有真實數據，創建一些示例數據
    if not interaction_links and not chat_length_links:
        print("No interaction data found, creating sample data...")
        sample_interactions = [
            ("盧品蓉", "魏祈紘", 15, 450),
            ("莊于萱", "施宇鴻", 12, 320),
            ("游庭瑄", "李昇峰", 25, 680),
            ("鄭傑丞", "游庭瑄", 8, 190),
            ("陳冠佑", "蔡宗陞", 18, 520),
            ("盧品蓉", "莊于萱", 6, 180),
            ("魏祈紘", "鄭傑丞", 9, 240),
            ("李昇峰", "陳冠佑", 7, 200),
            ("施宇鴻", "蔡宗陞", 5, 150),
            ("游庭瑄", "盧品蓉", 4, 120),
        ]
        
        for person1, person2, count, length in sample_interactions:
            if person1 in personas and person2 in personas:
                interaction_links.append({
                    "source": person1,
                    "target": person2,
                    "value": count
                })
                chat_length_links.append({
                    "source": person1,
                    "target": person2,
                    "length": length
                })

    # 構建返回數據
    interaction_data = {
        "nodes": nodes,
        "links": interaction_links
    }
    
    chat_length_data = {
        "nodes": nodes,
        "links": chat_length_links
    }

    print(f"Final data - Nodes: {len(nodes)}, Interaction links: {len(interaction_links)}, Chat length links: {len(chat_length_links)}")

    # 將數據作為JSON字符串傳遞給模板，避免在模板中進行復雜的數據處理
    return render_template(
        "interaction_graph.html",
        interaction_data=json.dumps(interaction_data, ensure_ascii=False),
        chat_length_data=json.dumps(chat_length_data, ensure_ascii=False),
        persona_names=personas
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
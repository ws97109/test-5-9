import os
import json
import collections
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify

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

    print(f"已載入對話數據: {len(conversation_data)} 個時間點")

    # 計算角色之間的互動次數和對話長度
    interactions = collections.defaultdict(int)
    chat_lengths = collections.defaultdict(int)
    
    interaction_details = []
    
    for time_key, interactions_list in conversation_data.items():
        print(f"時間點 {time_key}: {len(interactions_list)} 個互動")
        for interaction in interactions_list:
            # 每個互動記錄的鍵看起來像 "角色1 -> 角色2 @ 位置"
            for key, chat_history in interaction.items():
                print(f"互動鍵: {key}, 對話長度: {len(chat_history)}")
                parts = key.split(" -> ")
                if len(parts) == 2:
                    person1 = parts[0]
                    person2 = parts[1].split(" @ ")[0]
                    
                    print(f"解析出: {person1} -> {person2}")
                    
                    # 確保對話歷史是有效的
                    if not isinstance(chat_history, list):
                        print(f"警告: 對話歷史不是列表: {type(chat_history)}")
                        continue
                    
                    # 增加互動計數
                    interactions[(person1, person2)] += len(chat_history)
                    
                    # 計算對話總長度（字符數）
                    # 確保消息是字符串，避免TypeError
                    try:
                        total_length = sum(len(str(msg[1])) for msg in chat_history if isinstance(msg, list) and len(msg) > 1)
                        chat_lengths[(person1, person2)] += total_length
                        
                        # 記錄詳細信息用於調試
                        interaction_details.append({
                            "time": time_key,
                            "source": person1,
                            "target": person2,
                            "messages": len(chat_history),
                            "length": total_length,
                            "content": [str(msg) for msg in chat_history] if isinstance(chat_history, list) else str(chat_history)
                        })
                        
                        print(f"互動次數: {interactions[(person1, person2)]}, 對話長度: {chat_lengths[(person1, person2)]}")
                    except Exception as e:
                        print(f"處理對話時出錯: {e}, 對話內容: {chat_history}")

    # 創建D3.js力導向圖所需的數據格式
    nodes = [{"id": person, "group": 1} for person in personas]
    
    # 互動次數連接
    interaction_links = []
    for (person1, person2), count in interactions.items():
        if count > 0:  # 只添加有互動的連接
            interaction_links.append({
                "source": person1,
                "target": person2,
                "value": count
            })
    
    # 對話長度連接
    chat_length_links = []
    for (person1, person2), length in chat_lengths.items():
        if length > 0:  # 只添加有對話的連接
            chat_length_links.append({
                "source": person1,
                "target": person2,
                "length": length
            })
    
    print(f"節點數: {len(nodes)}")
    print(f"互動連接數: {len(interaction_links)}")
    print(f"對話長度連接數: {len(chat_length_links)}")
    
    interaction_data = {
        "nodes": nodes,
        "links": interaction_links
    }
    
    chat_length_data = {
        "nodes": nodes,
        "links": chat_length_links
    }
    
    # 將數據寫入臨時 JSON 文件用於調試
    try:
        with open("debug_data.json", "w", encoding="utf-8") as f:
            json.dump({
                "interaction_data": interaction_data,
                "chat_length_data": chat_length_data,
                "personas": personas,
                "interaction_details": interaction_details
            }, f, indent=2, ensure_ascii=False)
        print("調試數據已寫入 debug_data.json")
    except Exception as e:
        print(f"寫入調試數據時出錯: {e}")

    return render_template(
        "interaction_graph.html",
        interaction_data=interaction_data,
        chat_length_data=chat_length_data,
        personas=personas,
        interaction_details=interaction_details
    )


@app.route("/debug-data", methods=['GET'])
def debug_data():
    """提供調試數據的API端點"""
    try:
        with open("debug_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5001)

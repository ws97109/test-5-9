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


if __name__ == "__main__":
    app.run(debug=True,  port=5001)
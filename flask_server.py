from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/update_range', methods=['POST'])
def update_range():
    data = request.get_json()
    center_freq = data.get("center_frequency")  # In Hz
    bandwidth = data.get("bandwidth")           # In Hz

    if not center_freq or not bandwidth:
        return jsonify({"error": "Missing parameters"}), 400

    f_min = center_freq - bandwidth / 2
    f_max = center_freq + bandwidth / 2
    range_str = f"{f_min}e6-{f_max}e6"

    # Save this range to a file or an environment variable
    with open("/local/repository/freq_range.txt", "w") as f:
        f.write(range_str)

    return jsonify({"RANGE": range_str})

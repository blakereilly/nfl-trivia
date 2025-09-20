import os
import random
import pandas as pd
from flask import Flask, jsonify, request, session, render_template
from datetime import date

app = Flask(__name__)
app.secret_key = 'your_super_secret_key'

# --- Data & Game Configuration ---
base_dir = os.path.join(os.path.dirname(__file__), 'stats')
processed_data_path = os.path.join(base_dir, 'combined_stats.csv')
# NEW: Path for the shuffled daily player list
daily_player_order_path = os.path.join(base_dir, 'daily_player_order.csv') 
EARLIEST_YEAR = 2011
# NEW: The official "Day 1" of the FumbLe Daily Challenge
START_DATE = date(2025, 9, 20)

# (Team name and info dictionaries remain the same)
team_name_map = {
    'GNB': 'GB', 'LVR': 'LV', 'OAK': 'LV', 'NWE': 'NE', 'KAN': 'KC',
    'NOR': 'NO', 'TAM': 'TB', 'SFO': 'SF', 'WSH': 'WAS'
}
team_info = {
    'ARI': {'conf': 'NFC', 'div': 'West'}, 'ATL': {'conf': 'NFC', 'div': 'South'},
    'BAL': {'conf': 'AFC', 'div': 'North'}, 'BUF': {'conf': 'AFC', 'div': 'East'},
    'CAR': {'conf': 'NFC', 'div': 'South'}, 'CHI': {'conf': 'NFC', 'div': 'North'},
    'CIN': {'conf': 'AFC', 'div': 'North'}, 'CLE': {'conf': 'AFC', 'div': 'North'},
    'DAL': {'conf': 'NFC', 'div': 'East'}, 'DEN': {'conf': 'AFC', 'div': 'West'},
    'DET': {'conf': 'NFC', 'div': 'North'}, 'GB': {'conf': 'NFC', 'div': 'North'},
    'HOU': {'conf': 'AFC', 'div': 'South'}, 'IND': {'conf': 'AFC', 'div': 'South'},
    'JAX': {'conf': 'AFC', 'div': 'South'}, 'KC': {'conf': 'AFC', 'div': 'West'},
    'LAC': {'conf': 'AFC', 'div': 'West'}, 'LAR': {'conf': 'NFC', 'div': 'West'},
    'LV': {'conf': 'AFC', 'div': 'West'}, 'MIA': {'conf': 'AFC', 'div': 'East'},
    'MIN': {'conf': 'NFC', 'div': 'North'}, 'NE': {'conf': 'AFC', 'div': 'East'},
    'NO': {'conf': 'NFC', 'div': 'South'}, 'NYG': {'conf': 'NFC', 'div': 'East'},
    'NYJ': {'conf': 'AFC', 'div': 'East'}, 'PHI': {'conf': 'NFC', 'div': 'East'},
    'PIT': {'conf': 'AFC', 'div': 'North'}, 'SF': {'conf': 'NFC', 'div': 'West'},
    'SEA': {'conf': 'NFC', 'div': 'West'}, 'TB': {'conf': 'NFC', 'div': 'South'},
    'TEN': {'conf': 'AFC', 'div': 'South'}, 'WAS': {'conf': 'NFC', 'div': 'East'},
    'OAK': {'conf': 'AFC', 'div': 'West'}, 'SDG': {'conf': 'AFC', 'div': 'West'},
    'TOT': {'conf': 'N/A', 'div': 'N/A'}, 'FA': {'conf': 'N/A', 'div': 'N/A'}
}

# --- Data Loading and Pre-computation ---
# (This logic now includes generating the one-time shuffled list)
if os.path.exists(processed_data_path):
    print("Loading data from cached file...")
    combined_df = pd.read_csv(processed_data_path)
else:
    # (Data processing logic remains the same)
    print("No cached file found. Loading and combining raw data...")
    all_dfs = []
    years = range(2010, 2025)
    for year in years:
        file_name = f'player_stats{year}.csv'
        file_path = os.path.join(base_dir, file_name)
        if not os.path.exists(file_path) or not os.access(file_path, os.R_OK):
            continue
        try:
            df = pd.read_csv(file_path)
            if 'Player' not in df.columns: continue
            df['Tm'] = df['Tm'].replace(team_name_map)
            df['Year'] = year
            all_dfs.append(df)
        except Exception as e:
            print(f"Error loading {file_name}: {e}")
            continue
    if not all_dfs:
        print("Error: No data files found. Exiting.")
        exit()
    combined_df = pd.concat(all_dfs, ignore_index=True)
    combined_df = combined_df.rename(columns={'Yds': 'PassYds', 'TD': 'PassTD', 'Yds.1': 'RushYds', 'TD.1': 'RushTD', 'Yds.2': 'RecYds', 'TD.2': 'RecTD'})
    int_cols = ['G', 'PassYds', 'PassTD', 'RushYds', 'RushTD', 'Rec', 'RecYds', 'RecTD']
    for col in int_cols:
        if col in combined_df.columns:
            combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce').fillna(0).astype(int)
    if 'PPR' in combined_df.columns:
        combined_df['PPR'] = pd.to_numeric(combined_df['PPR'], errors='coerce').fillna(0)
    combined_df['Player'] = combined_df['Player'].str.replace(r'[^\w\s-]*$', '', regex=True)
    combined_df['Conference'] = combined_df['Tm'].apply(lambda x: team_info.get(x, {}).get('conf', 'N/A'))
    combined_df['Division'] = combined_df['Tm'].apply(lambda x: team_info.get(x, {}).get('div', 'N/A'))
    combined_df['PPR_Rank_by_Pos'] = combined_df.groupby(['Year', 'FantPos'])['PPR'].rank(ascending=False, method='dense').astype(int)
    combined_df = combined_df[combined_df['FantPos'] != 'FB'].copy()
    combined_df.to_csv(processed_data_path, index=False)
    print("Data processing complete and saved.")

# (Player filtering logic remains the same)
player_first_year = combined_df.groupby('Player')['Year'].min().reset_index()
player_first_year.rename(columns={'Year': 'FirstYear'}, inplace=True)
eligible_players_df = pd.merge(combined_df, player_first_year, on='Player')
top_24_seasons = eligible_players_df[eligible_players_df['PPR_Rank_by_Pos'] <= 24]
players_with_2_top_24_seasons = top_24_seasons['Player'].value_counts()
valid_players_24 = players_with_2_top_24_seasons[players_with_2_top_24_seasons >= 2].index.tolist()
top_12_seasons = eligible_players_df[eligible_players_df['PPR_Rank_by_Pos'] <= 12]
valid_players_12 = top_12_seasons['Player'].unique().tolist()
eligible_players_list = list(set(valid_players_24 + valid_players_12))
eligible_players_prefiltered = eligible_players_df[
    (eligible_players_df['Player'].isin(eligible_players_list)) &
    (eligible_players_df['FirstYear'] >= EARLIEST_YEAR) &
    (eligible_players_df['Year'] >= EARLIEST_YEAR)
].copy()

# NEW: Generate and save the shuffled player list if it doesn't exist
if not os.path.exists(daily_player_order_path):
    print("Creating shuffled daily player list...")
    daily_players = eligible_players_prefiltered['Player'].unique().tolist()
    random.shuffle(daily_players)
    pd.DataFrame(daily_players, columns=['Player']).to_csv(daily_player_order_path, index=False)
    print("Daily player list created and saved.")

# NEW: Load the ordered list of daily players
daily_player_list = pd.read_csv(daily_player_order_path)['Player'].tolist()
print(f"{len(daily_player_list)} daily players loaded.")

def get_most_frequent_with_tiebreaker(df, column):
    if df.empty: return "N/A"
    counts = df[column].value_counts()
    if counts.empty: return "N/A"
    max_seasons = counts.max()
    tied_values = counts[counts == max_seasons].index.tolist()
    if len(tied_values) == 1: return tied_values[0]
    else:
        most_recent_year, most_recent_value = 0, "N/A"
        for value in tied_values:
            most_recent_season_for_value = df[df[column] == value]['Year'].max()
            if most_recent_season_for_value > most_recent_year:
                most_recent_year = most_recent_season_for_value
                most_recent_value = value
        return most_recent_value

# --- Flask Routes ---
@app.route('/')
def home():
    return render_template('landing.html')

@app.route('/game')
def game_page():
    return render_template('game.html')

# MODIFIED: This route is now the daily game starter
@app.route('/start_game', methods=['POST'])
def start_game():
    today = date.today()
    days_since_start = (today - START_DATE).days

    if days_since_start < 0:
        return jsonify({"error": "The daily challenge has not started yet!"})

    # Select player based on the day number
    player_index = days_since_start % len(daily_player_list)
    selected_player_name = daily_player_list[player_index]
    
    player_history_df = eligible_players_prefiltered[eligible_players_prefiltered['Player'] == selected_player_name].copy()
    player_history_df = player_history_df.sort_values(by='Year')

    if player_history_df.empty:
        return jsonify({"error": f"Could not find data for daily player: {selected_player_name}"})

    most_frequent_team = get_most_frequent_with_tiebreaker(player_history_df, 'Tm')
    team_details = team_info.get(most_frequent_team, {})
    consistent_conference = team_details.get('conf', 'N/A')
    consistent_division = team_details.get('div', 'N/A')
    selected_player_position = player_history_df.iloc[0]['FantPos']
    
    # Session setup remains largely the same
    session['correct_player_name'] = selected_player_name.lower()
    session['guesses_remaining'] = 4
    session['correct_last_name'] = selected_player_name.lower().split()[-1]
    session['hints'] = {
        'conference': consistent_conference, 'division': consistent_division, 'team': most_frequent_team
    }
    
    stats_json = player_history_df.to_dict('records')
    return jsonify({'position': selected_player_position, 'stats': stats_json})

# (Suggest, Guess, Hint, and Give Up routes remain the same)
@app.route('/suggest_players', methods=['POST'])
def suggest_players():
    data = request.get_json()
    query = data.get('query', '').strip().lower()
    position = session.get('correct_player', {}).get('FantPos')
    if not query or len(query) < 2 or not position:
        return jsonify([])
    filtered_df = eligible_players_prefiltered[
        (eligible_players_prefiltered['FantPos'] == position) &
        (eligible_players_prefiltered['Player'].str.lower().str.contains(query, na=False))
    ]
    unique_players = filtered_df['Player'].unique().tolist()
    return jsonify(unique_players[:10])

@app.route('/guess', methods=['POST'])
def handle_guess():
    guess = request.get_json().get('guess', '').strip().lower()
    if 'guesses_remaining' not in session:
        return jsonify({"error": "Game not started. Please refresh."}), 400
    correct_last_name = session['correct_last_name']
    guess_last_name = guess.split()[-1].lower()
    if guess == session['correct_player_name'] or guess_last_name == correct_last_name:
        correct_name = session['correct_player_name'].title()
        guesses_taken = 4 - session.get('guesses_remaining', 0) + 1
        session.clear() # Clear session on win
        return jsonify({'result': 'correct', 'message': f"🎉 Correct! The player is **{correct_name}**.", 'guesses_taken': guesses_taken})
    else:
        session['guesses_remaining'] -= 1
        tries_left = session['guesses_remaining']
        if tries_left > 0:
            hint = ""
            if tries_left == 3: hint = f"Hint: This player spent most of their seasons in the **{session['hints']['conference']}**."
            elif tries_left == 2: hint = f"Hint: This player spent most of their seasons in the **{session['hints']['conference']} {session['hints']['division']}**."
            elif tries_left == 1: hint = f"Hint: This player spent most of their seasons with **{session['hints']['team']}**."
            return jsonify({'result': 'incorrect', 'message': "❌ Incorrect guess.", 'hint': hint, 'guesses_left': tries_left, 'is_last_guess': tries_left == 1})
        else:
            final_message = f"❌ Out of guesses! The correct player was **{session['correct_player_name'].title()}**."
            session.clear() # Clear session on loss
            return jsonify({'result': 'out_of_guesses', 'message': final_message, 'guesses_taken': 4})

@app.route('/hint', methods=['POST'])
def get_hint():
    guesses_left = session.get('guesses_remaining')
    if guesses_left is None or guesses_left <= 1:
        return jsonify({'message': 'You cannot use a hint on your last guess!'}), 400
    session['guesses_remaining'] -= 1
    current_guesses = session['guesses_remaining']
    hints = session.get('hints')
    hint_message = ""
    if current_guesses == 3: hint_message = f"Hint: This player spent most of their seasons in the **{hints['conference']}**."
    elif current_guesses == 2: hint_message = f"Hint: This player spent most of their seasons in the **{hints['conference']} {hints['division']}**."
    elif current_guesses == 1: hint_message = f"Hint: This player spent most of their seasons with **{hints['team']}**."
    return jsonify({'message': hint_message, 'guesses_left': current_guesses, 'is_last_guess': current_guesses == 1})

@app.route('/give_up', methods=['POST'])
def give_up():
    if 'correct_player_name' not in session:
        return jsonify({"error": "Game not started. Please refresh."}), 400
    final_message = f"The correct player was **{session['correct_player_name'].title()}**. Better luck next time!"
    session.clear() # Clear session on give up
    return jsonify({'result': 'out_of_guesses', 'message': final_message, 'guesses_taken': 4})


if __name__ == '__main__':
    if not os.path.exists('templates'):
        os.makedirs('templates')
    app.run(debug=True, port=5000)


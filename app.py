import os
import hashlib
import random
from datetime import date, datetime
from zoneinfo import ZoneInfo
import pandas as pd
from flask import Flask, jsonify, request, session, render_template
#Above lines import py classes needed. os for file paths and flask for hosting webapp

#Creates instance of flask webapp
app = Flask(__name__)
app.secret_key = 'your_super_secret_key'  # Change this to a secure secret key

#Locates full stats and combined stats files
# --- Data Processing and Pre-filtering (Runs Once) ---
base_dir = os.path.join(os.path.dirname(__file__), 'stats')
processed_data_path = os.path.join(base_dir, 'combined_stats.csv')
#Define earliest year for eligible players
EARLIEST_YEAR = 2011
years = range(2010, 2026)
#Initialize data frames as a list
all_dfs = []

#Create map for team names to normalize with team info
team_name_map = {
    'GNB': 'GB', 'LVR': 'LV', 'OAK': 'LV', 'NWE': 'NE', 'KAN': 'KC',
    'NOR': 'NO', 'TAM': 'TB', 'SFO': 'SF', 'WSH': 'WAS'
}

#Create map for player hints
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

#Check if combined stats file already exists to avoid repeating data processing
if os.path.exists(processed_data_path):
    print("Loading data from cached file...")
    #keep_default_na/na_values guard against pandas re-reading our own literal "N/A" strings
    #(e.g. Conference/Division for multi-team "2TM" seasons) back in as real NaN floats
    combined_df = pd.read_csv(processed_data_path, keep_default_na=False, na_values=[''])
    print("Data loaded instantly!")
else:
    #Take individual yearly stats files and combine into one large combined csv file
    print("No cached file found. Generating new data file...")
    for year in years:
        file_name = f'player_stats{year}.csv'
        file_path = os.path.join(base_dir, file_name)
        if not os.path.exists(file_path) or not os.access(file_path, os.R_OK): continue
        try:
            df = pd.read_csv(file_path)
            if 'Player' not in df.columns: continue
            df['Tm'] = df['Tm'].replace(team_name_map)
            df['Year'] = year
            all_dfs.append(df)
        except Exception as e:
            print(f"Error loading or processing {file_name}: {e}")
            continue
    if not all_dfs:
        print("Error: No data files found. Exiting.")
        exit()
    
    combined_df = pd.concat(all_dfs, ignore_index=True)
    combined_df = combined_df.rename(columns={'Yds': 'PassYds', 'TD': 'PassTD', 'Yds.1': 'RushYds', 'TD.1': 'RushTD', 'Yds.2': 'RecYds', 'TD.2': 'RecTD'})
    int_cols = ['G', 'PassYds', 'PassTD', 'RushYds', 'RushTD', 'Rec', 'RecYds', 'RecTD']
    float_cols = ['PPR']
    for col in int_cols:
        if col in combined_df.columns: combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce').fillna(0).astype(int)
    for col in float_cols:
        if col in combined_df.columns: combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce').fillna(0)
    
    combined_df['Player'] = combined_df['Player'].str.replace(r'[^\w\s-]*$', '', regex=True)
    combined_df['Conference'] = combined_df['Tm'].apply(lambda x: team_info.get(x, {}).get('conf', 'N/A'))
    combined_df['Division'] = combined_df['Tm'].apply(lambda x: team_info.get(x, {}).get('div', 'N/A'))
    combined_df['PPR_Rank'] = combined_df.groupby('Year')['PPR'].rank(ascending=False, method='dense').astype(int)
    combined_df['PPR_Rank_by_Pos'] = combined_df.groupby(['Year', 'FantPos'])['PPR'].rank(ascending=False, method='dense').astype(int)
    combined_df = combined_df[combined_df['FantPos'] != 'FB'].copy()

    #Difficulty calculator. But something is wrong with it
    #It should calculate dificulties only on eligible players but it's doing it for each player each season
    # --- START: One-Time Difficulty Calculation ---
    print("Calculating player difficulty ratings for the first time...")
    CONFIG = {
        'weights': {'performance': 0, 'longevity': 0.15, 'recency': 0.30, 'star_power': 0.55},
        'multipliers': {'QB': 0.85, 'RB': 1.0, 'WR': 1.0, 'TE': 1.25},
        'max_rank_cap': 100,
        'good_season_rank_threshold': 24,
        'star_tiers': {
            'legendary': {'ranks': range(1, 2), 'points': 15}, 'elite': {'ranks': range(2, 4), 'points': 10},
            'great': {'ranks': range(4, 13), 'points': 5}, 'good': {'ranks': range(13, 25), 'points': 2}
        }
    }

    def calculate_component_scores(player_group, global_stats):
        median_rank = player_group['PPR_Rank_by_Pos'].median()
        capped_rank = min(median_rank, CONFIG['max_rank_cap'])
        perf_score = (capped_rank - 1) / (CONFIG['max_rank_cap'] - 1)
        num_seasons = player_group['Year'].nunique()
        longevity_score = (global_stats['max_seasons'] - num_seasons) / (global_stats['max_seasons'] - global_stats['min_seasons'])
        good_seasons = player_group[player_group['PPR_Rank_by_Pos'] <= CONFIG['good_season_rank_threshold']]
        last_relevant_season = good_seasons['Year'].max() if not good_seasons.empty else player_group['Year'].max()
        recency_score = (global_stats['max_year'] - last_relevant_season) / (global_stats['max_year'] - global_stats['min_year'])
        total_star_points = 0
        for rank in player_group['PPR_Rank_by_Pos']:
            if rank in CONFIG['star_tiers']['legendary']['ranks']: total_star_points += CONFIG['star_tiers']['legendary']['points']
            elif rank in CONFIG['star_tiers']['elite']['ranks']: total_star_points += CONFIG['star_tiers']['elite']['points']
            elif rank in CONFIG['star_tiers']['great']['ranks']: total_star_points += CONFIG['star_tiers']['great']['points']
            elif rank in CONFIG['star_tiers']['good']['ranks']: total_star_points += CONFIG['star_tiers']['good']['points']
        avg_points_per_season = total_star_points / num_seasons if num_seasons > 0 else 0
        return pd.Series({'perf_score': perf_score, 'longevity_score': longevity_score, 'recency_score': recency_score, 'star_points': avg_points_per_season, 'position': player_group['FantPos'].iloc[0]})

    temp_eligible_df = combined_df.copy()
    player_seasons = temp_eligible_df.groupby('Player')['Year'].nunique()
    global_stats = {'min_seasons': player_seasons.min(), 'max_seasons': player_seasons.max(), 'min_year': temp_eligible_df['Year'].min(), 'max_year': temp_eligible_df['Year'].max()}
    
    component_scores = temp_eligible_df.groupby('Player').apply(calculate_component_scores, global_stats)
    max_star_points = component_scores['star_points'].max()
    component_scores['star_score'] = 1 - (component_scores['star_points'] / max_star_points)
    
    w = CONFIG['weights']
    raw_scores = (w['performance'] * component_scores['perf_score'] + w['longevity'] * component_scores['longevity_score'] + w['recency'] * component_scores['recency_score'] + w['star_power'] * component_scores['star_score'])
    pos_multipliers = component_scores['position'].map(CONFIG['multipliers']).fillna(1.0)
    raw_scores *= pos_multipliers
    
    min_raw_score = raw_scores.min()
    max_raw_score = raw_scores.max()
    difficulty_ratings = 1 + 9 * (raw_scores - min_raw_score) / (max_raw_score - min_raw_score)
    difficulty_ratings = difficulty_ratings.round(1).reset_index(name='Difficulty')
    
    combined_df = pd.merge(combined_df, difficulty_ratings, on='Player', how='left')
    # --- END: One-Time Difficulty Calculation ---

    combined_df.to_csv(processed_data_path, index=False)
    print("Data processing complete and saved with difficulty ratings.")

#Define player eligibility to only allow players with certain criteria
# --- Player Eligibility and Final DataFrame Preparation ---
if 'Player' not in combined_df.columns:
    print("Fatal Error: 'Player' column is missing. Cannot proceed.")
    exit()

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
    (eligible_players_df['FirstYear'] >= EARLIEST_YEAR)
].copy()

if eligible_players_prefiltered.empty:
    print(f"Warning: No eligible players found for starting year {EARLIEST_YEAR}.")
print(f"All eligible players pre-filtered and stored!")

#Daily game setup: split eligible players into three balanced difficulty tiers and
#build a deterministic per-tier rotation so every visitor sees the same players on a
#given calendar day, with no repeats until a tier's whole pool has been used.
GAME_TZ = ZoneInfo("America/New_York")
EPOCH_DATE = date(2024, 1, 1)
ROUND_TIERS = ['easy', 'hard']
TIER_LABELS = {'easy': 'Easy', 'hard': 'Hard'}
FAIL_PENALTY = 5

def today_str():
    return datetime.now(GAME_TZ).date().isoformat()

def deterministic_shuffle(players, salt):
    return sorted(players, key=lambda p: hashlib.md5(f"{p}|{salt}".encode()).hexdigest())

player_difficulty_df = eligible_players_prefiltered.drop_duplicates('Player')[['Player', 'Difficulty']].dropna(subset=['Difficulty'])
player_difficulty_df = player_difficulty_df.sort_values('Difficulty').reset_index(drop=True)
_n = len(player_difficulty_df)
_mid = _n // 2
TIER_POOLS = {
    'easy': player_difficulty_df.iloc[:_mid]['Player'].tolist(),
    'hard': player_difficulty_df.iloc[_mid:]['Player'].tolist(),
}
TIER_ROTATIONS = {tier: deterministic_shuffle(players, tier) for tier, players in TIER_POOLS.items()}

#Dev-only override so local testing isn't locked to the same 2 players all day (see /dev/new_game)
def get_daily_player(tier, game_date, seed_override=None):
    rotation = TIER_ROTATIONS[tier]
    day_index = seed_override if seed_override is not None else (game_date - EPOCH_DATE).days
    return rotation[day_index % len(rotation)]

#If a player has played for different teams for same amount of seasons, tiebreaker goes to recent.
#This function is called within the game routes
def get_most_frequent_with_tiebreaker(df, column):
    if df.empty: return "N/A"
    counts = df[column].value_counts()
    if counts.empty: return "N/A"
    max_seasons = counts.max()
    tied_values = counts[counts == max_seasons].index.tolist()
    if len(tied_values) == 1: return tied_values[0]
    else:
        most_recent_year = 0
        most_recent_value = "N/A"
        for value in tied_values:
            most_recent_season_for_value = df[df[column] == value]['Year'].max()
            if most_recent_season_for_value > most_recent_year:
                most_recent_year = most_recent_season_for_value
                most_recent_value = value
        return most_recent_value


#Start of API endpoints. These are the routes called by the front end javascript

#Builds the position/stats/hints payload for a given player without touching session state
def get_player_payload(selected_player_name):
    player_history_df = eligible_players_prefiltered[eligible_players_prefiltered['Player'] == selected_player_name].copy()
    player_history_df = player_history_df.sort_values(by='Year', ascending=False)
    player_difficulty = player_history_df.iloc[0]['Difficulty']
    most_frequent_team = get_most_frequent_with_tiebreaker(player_history_df, 'Tm')
    team_details = team_info.get(most_frequent_team, {})
    consistent_conference = team_details.get('conf', 'N/A')
    consistent_division = team_details.get('div', 'N/A')
    selected_player_position = player_history_df.iloc[0]['FantPos']
    rookie_year = int(player_history_df.iloc[0]['FirstYear']) if 'FirstYear' in player_history_df.columns else None
    all_columns = ['Year', 'FantPos', 'Tm', 'Conference', 'Division', 'G', 'PPR_Rank_by_Pos', 'PPR', 'PassYds', 'PassTD', 'RushYds', 'RushTD', 'Rec', 'RecYds', 'RecTD']
    columns_to_show = [col for col in all_columns if col in player_history_df.columns]
    stats_json = player_history_df[columns_to_show].to_dict('records')
    return {
        'position': selected_player_position,
        'stats': stats_json,
        'difficulty': player_difficulty,
        'hints': {'conference': consistent_conference, 'division': consistent_division, 'team': most_frequent_team},
        'last_name': selected_player_name.lower().split()[-1],
        'rookie_year': rookie_year,
    }

#Resets round progress whenever the calendar day (in GAME_TZ) has rolled over
def ensure_daily_session():
    today = today_str()
    if session.get('game_date') != today:
        session['game_date'] = today
        session['round_index'] = 0
        session['round_results'] = []
        for key in ['correct_player_name', 'correct_player_display', 'guesses_remaining', 'correct_last_name', 'hints', 'current_tier', 'current_position', 'dev_seed']:
            session.pop(key, None)

def begin_round(player_name, tier):
    info = get_player_payload(player_name)
    session['correct_player_name'] = player_name.lower()
    session['correct_player_display'] = player_name
    session['correct_last_name'] = info['last_name']
    session['guesses_remaining'] = 4
    session['hints'] = info['hints']
    session['current_tier'] = tier
    session['current_position'] = info['position']
    return {
        'tier': tier,
        'round_number': ROUND_TIERS.index(tier) + 1,
        'total_rounds': len(ROUND_TIERS),
        'position': info['position'],
        'stats': info['stats'],
        'difficulty': info['difficulty'],
        'rookie_year': info['rookie_year'],
        'guesses_left': 4,
        'resumed': False,
    }

#Rebuilds the current round's payload without re-rolling or resetting guesses (used on page refresh)
def resume_round():
    tier = session['current_tier']
    info = get_player_payload(session['correct_player_display'])
    return {
        'tier': tier,
        'round_number': ROUND_TIERS.index(tier) + 1,
        'total_rounds': len(ROUND_TIERS),
        'position': info['position'],
        'stats': info['stats'],
        'difficulty': info['difficulty'],
        'rookie_year': info['rookie_year'],
        'guesses_left': session.get('guesses_remaining', 4),
        'resumed': True,
    }

def complete_round(solved, score):
    tier = session.get('current_tier')
    round_results = session.get('round_results', [])
    round_results.append({'tier': tier, 'label': TIER_LABELS.get(tier, tier), 'score': score, 'solved': solved})
    session['round_results'] = round_results
    session['round_index'] = session.get('round_index', 0) + 1
    for key in ['correct_player_name', 'correct_player_display', 'guesses_remaining', 'correct_last_name', 'hints', 'current_tier', 'current_position']:
        session.pop(key, None)
    daily_complete = session['round_index'] >= len(ROUND_TIERS)
    return {
        'round_complete': True,
        'daily_complete': daily_complete,
        'next_tier': ROUND_TIERS[session['round_index']] if not daily_complete else None,
        'total_rounds': len(ROUND_TIERS),
        'round_results': round_results,
        'total_score': sum(r['score'] for r in round_results),
        'date': session['game_date'],
    }

#Render and return Landing Page html
@app.route('/')
def home():
    return render_template('landing.html')

#Render and return Game html
@app.route('/game')
def game_page():
    return render_template('game.html', dev_mode=app.debug)

#Tells the frontend where the player is in today's game so a refresh resumes correctly
@app.route('/daily_status', methods=['GET'])
def daily_status():
    ensure_daily_session()
    round_index = session.get('round_index', 0)
    round_results = session.get('round_results', [])
    is_complete = round_index >= len(ROUND_TIERS)
    return jsonify({
        'date': session['game_date'],
        'round_index': round_index,
        'current_tier': ROUND_TIERS[round_index] if not is_complete else None,
        'total_rounds': len(ROUND_TIERS),
        'round_results': round_results,
        'total_score': sum(r['score'] for r in round_results),
        'is_complete': is_complete,
        'in_progress': 'correct_player_name' in session,
    })

#Dev-only: start a fresh game with a random day-seed instead of the real date, so local
#testing isn't locked to the same 2 players until tomorrow. Disabled unless Flask debug is on.
@app.route('/dev/new_game', methods=['POST'])
def dev_new_game():
    if not app.debug:
        return jsonify({'error': 'not available'}), 404
    session['game_date'] = today_str()
    session['dev_seed'] = random.randint(0, 1_000_000)
    session['round_index'] = 0
    session['round_results'] = []
    for key in ['correct_player_name', 'correct_player_display', 'guesses_remaining', 'correct_last_name', 'hints', 'current_tier', 'current_position']:
        session.pop(key, None)
    return jsonify({'ok': True})

#This is where the magic happens
@app.route('/start_game', methods=['POST'])
def start_game():
    ensure_daily_session()
    round_index = session.get('round_index', 0)
    if round_index >= len(ROUND_TIERS):
        round_results = session.get('round_results', [])
        return jsonify({
            'error': 'daily_complete',
            'round_results': round_results,
            'total_score': sum(r['score'] for r in round_results),
        })
    tier = ROUND_TIERS[round_index]
    #If this round is already in progress (e.g. page refresh), resume it instead of re-rolling a player
    if session.get('current_tier') == tier and 'correct_player_name' in session:
        return jsonify(resume_round())
    game_date = date.fromisoformat(session['game_date'])
    player_name = get_daily_player(tier, game_date, seed_override=session.get('dev_seed'))
    return jsonify(begin_round(player_name, tier))

@app.route('/suggest_players', methods=['POST'])
def suggest_players():
    data = request.get_json()
    query = data.get('query', '').strip().lower()
    position = session.get('current_position')
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
        round_info = complete_round(solved=True, score=guesses_taken)
        return jsonify({
            **round_info,
            'result': 'correct',
            'message': f"🎉 Correct! The player is **{correct_name}**.",
            'guesses_taken': guesses_taken,
        })
    else:
        session['guesses_remaining'] -= 1
        tries_left = session['guesses_remaining']
        if tries_left > 0:
            hint = ""
            if tries_left == 3:
                hint = f"Hint: This player spent most of their seasons in the **{session['hints']['conference']}**."
            elif tries_left == 2:
                hint = f"Hint: This player spent most of their seasons in the **{session['hints']['conference']} {session['hints']['division']}**."
            elif tries_left == 1:
                hint = f"Hint: This player spent most of their seasons with **{session['hints']['team']}**."

            return jsonify({
                'result': 'incorrect',
                'message': "❌ Incorrect guess.",
                'hint': hint,
                'guesses_left': tries_left,
                'is_last_guess': tries_left == 1
            })
        else:
            correct_name = session['correct_player_name'].title()
            round_info = complete_round(solved=False, score=FAIL_PENALTY)
            final_message = f"❌ Out of guesses! The correct player was **{correct_name}**."
            return jsonify({
                **round_info,
                'result': 'out_of_guesses',
                'message': final_message,
                'guesses_taken': 4,
            })

@app.route('/hint', methods=['POST'])
def get_hint():
    guesses_left = session.get('guesses_remaining')
    if guesses_left is None or guesses_left <= 1:
        return jsonify({'message': 'You cannot use a hint on your last guess!'}), 400

    session['guesses_remaining'] -= 1
    current_guesses = session['guesses_remaining']

    hints = session.get('hints')
    hint_message = ""
    if current_guesses == 3:
        hint_message = f"Hint: This player spent most of their seasons in the **{hints['conference']}**."
    elif current_guesses == 2:
        hint_message = f"Hint: This player spent most of their seasons in the **{hints['conference']} {hints['division']}**."
    elif current_guesses == 1:
        hint_message = f"Hint: This player spent most of their seasons with **{hints['team']}**."

    return jsonify({
        'message': hint_message,
        'guesses_left': current_guesses,
        'is_last_guess': current_guesses == 1
    })

@app.route('/give_up', methods=['POST'])
def give_up():
    if 'correct_player_name' not in session:
        return jsonify({"error": "Game not started. Please refresh."}), 400
    correct_name = session['correct_player_name'].title()
    round_info = complete_round(solved=False, score=FAIL_PENALTY)
    final_message = f"The correct player was **{correct_name}**. Better luck next time!"
    return jsonify({
        **round_info,
        'result': 'out_of_guesses',
        'message': final_message,
        'guesses_taken': 4,
    })

if __name__ == '__main__':
    if not os.path.exists('templates'):
        os.makedirs('templates')
    app.run(debug=True, port=5000)
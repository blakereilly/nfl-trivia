import os
import random
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
years = range(2010, 2025)
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
    combined_df = pd.read_csv(processed_data_path)
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

#Render and return Landing Page html
@app.route('/')
def home():
    return render_template('landing.html')

#Render and return Game html
@app.route('/game')
def game_page():
    return render_template('game.html')

#This is where the magic happens
@app.route('/start_game', methods=['POST'])
def start_game():
    players_for_year = eligible_players_prefiltered.copy()
    if players_for_year.empty:
        return jsonify({"error": "No eligible players found for the configured year range."})
    #Randomly select a player from pre-filtered list
    selected_player_name = random.choice(players_for_year['Player'].unique().tolist())
    #Create new data frame with players stat history then sort it by year
    player_history_df = players_for_year[players_for_year['Player'] == selected_player_name].copy()
    player_history_df = player_history_df.sort_values(by='Year',  ascending=False)

    #Store player difficulty as a single variable for displaying later
    player_difficulty = player_history_df.iloc[0]['Difficulty']

    most_frequent_team = get_most_frequent_with_tiebreaker(player_history_df, 'Tm')
    team_details = team_info.get(most_frequent_team, {})
    consistent_conference = team_details.get('conf', 'N/A')
    consistent_division = team_details.get('div', 'N/A')
    selected_player_position = player_history_df.iloc[0]['FantPos']
    all_columns = ['Year', 'FantPos', 'G', 'PPR_Rank_by_Pos', 'PPR', 'PassYds', 'PassTD', 'RushYds', 'RushTD', 'Rec', 'RecYds', 'RecTD']
    columns_to_show = [col for col in all_columns if col in player_history_df.columns]
    display_df = player_history_df[columns_to_show]
    stats_json = display_df.to_dict('records')
    session['correct_player_name'] = selected_player_name.lower()
    session['correct_player'] = player_history_df.iloc[0].to_dict()
    session['guesses_remaining'] = 4
    session['correct_last_name'] = selected_player_name.lower().split()[-1]
    session['hints'] = {
        'conference': consistent_conference,
        'division': consistent_division,
        'team': most_frequent_team
    }
    return jsonify({
        'position': selected_player_position, 
        'stats': stats_json,
        'difficulty': player_difficulty
    })

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
        session.pop('guesses_remaining', None)
        return jsonify({'result': 'correct', 'message': f"🎉 Correct! The player is **{correct_name}**.", 'guesses_taken': guesses_taken})
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
            final_message = f"❌ Out of guesses! The correct player was **{session['correct_player_name'].title()}**."
            session.pop('guesses_remaining', None)
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
        
    final_message = f"The correct player was **{session['correct_player_name'].title()}**. Better luck next time!"
    session.pop('guesses_remaining', None)
    return jsonify({'result': 'out_of_guesses', 'message': final_message, 'guesses_taken': 4})

if __name__ == '__main__':
    if not os.path.exists('templates'):
        os.makedirs('templates')
    app.run(debug=True, port=5000)
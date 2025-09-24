# --- Data Processing and Pre-filtering (Runs Once) ---
base_dir = os.path.join(os.path.dirname(__file__), 'stats')
processed_data_path = os.path.join(base_dir, 'combined_stats.csv')
EARLIEST_YEAR = 2011
years = range(2010, 2025)
all_dfs = []

# (Team name map and team info dictionaries remain unchanged)
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

if os.path.exists(processed_data_path):
    print("Loading data from cached file...")
    combined_df = pd.read_csv(processed_data_path)
    print("Data loaded instantly!")
else:
    print("No cached file found. Generating new data file...")
    # (Data loading and combining logic remains unchanged)
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

    # --- START: One-Time Difficulty Calculation ---
    # This entire block now runs only once during file creation.
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
        # (This function is the same as before)
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

    temp_eligible_df = combined_df.copy() # Use a temporary df for calculation
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
    
    # Merge the final difficulty into the main DataFrame
    combined_df = pd.merge(combined_df, difficulty_ratings, on='Player', how='left')
    # --- END: One-Time Difficulty Calculation ---

    # Finally, save the enriched file
    combined_df.to_csv(processed_data_path, index=False)
    print("Data processing complete and saved with difficulty ratings.")


# --- Player Eligibility and Final DataFrame Preparation ---
# This section is now much simpler, as the heavy lifting is already done.
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
print("All eligible players pre-filtered and stored!")
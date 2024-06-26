import scipy.io as sio
import numpy as np
import pandas as pd
import os
import h5py
from datetime import datetime
from pathlib import Path
import warnings

warnings.filterwarnings('ignore')

def exclude_neurons(spikeData,sessionData,min_fire,quality):

    for session in sessionData['session_ID']:
        current_ses = sessionData[sessionData['session_ID'] == session]
        dur = int((current_ses['t_stop'] - current_ses['t_start']) / 1e6)
        spikes_ses = spikeData[spikeData['session_ID'] == session]
        n_spikes = (spikes_ses['ts'].apply(len))
        spikes_ses['fr'] = (spikes_ses['ts'].apply(len)) / dur
        spikes_ses = spikes_ses[spikes_ses['fr'] > min_fire]
        #spikes_ses = spikes_ses[spikes_ses['quality'] == quality]
        if not 'spikeData_excl' in locals():
            spikeData_excl = spikes_ses
        else:
            spikeData_excl = pd.concat([spikeData_excl, spikes_ses], axis=0)

    return spikeData_excl


def load_mat_file(file_path, variable_name):
    try:
        # Try loading with scipy.io.loadmat
        data = sio.loadmat(file_path, squeeze_me=True)
        if variable_name in data:
            return data[variable_name]
    except NotImplementedError:
        # If scipy.io.loadmat fails, try loading with h5py
        with h5py.File(file_path, 'r') as f:
            dGroup = f[variable_name]
            # print({key: f[variable_name][key][0] for key in f[variable_name].keys()})

            data = {key: f[variable_name][key] for key in f[variable_name].keys()}
            return {key: np.array(resolve_hdf5_reference(data[key][0, 0], f)) for key in data.keys()}


def resolve_hdf5_reference(reference, file):
    try:
        if isinstance(reference, h5py.Reference):
            return file[reference]
        elif isinstance(reference, np.ndarray) and reference.dtype == h5py.ref_dtype:
            return np.array([file[ref] for ref in reference])
    except Exception as e:
        print(f"Failed to resolve HDF5 reference: {e}")
    return reference


def convert_to_dataframe(data, dtype, file_path=None):
    if isinstance(data, dict):
        data_dict = data
    else:
        # Handle the case when data is loaded with scipy.io.loadmat
        data_dict = {x: data[x].item() for x in data.dtype.names}
        data_dict = {key: np.array(data_dict[key]) for key in data_dict.keys()}


    if (dtype == "sessionData") or (dtype == "videoData"):
        for var in data_dict:
            if isinstance(data_dict[var], np.ndarray):
                data_dict[var] = [data_dict[var]]

    return pd.DataFrame(data_dict)


def load_data(path_root, experiment):
    all_sessions = []
    data_types = ['trialData', 'sessionData', 'spikeData', 'videoData']
    trialData = pd.DataFrame()
    sessionData = pd.DataFrame()
    spikeData = pd.DataFrame()
    videoData = pd.DataFrame()

    for exp in experiment:
        animals = os.listdir(os.path.join(path_root, exp))
        for anml in animals:
            if anml == '.DS_Store':
                continue
            sessions = os.listdir(os.path.join(path_root, exp, anml))
            for ses in sessions:
                if not all(os.path.exists(os.path.join(path_root, exp, anml, ses, f'{dtype}.mat')) for dtype in data_types):
                    continue
                all_sessions.append(os.path.join(path_root, exp, anml, ses))

    for ses in all_sessions:
        for dtype in data_types:
            file_path = os.path.join(ses, f'{dtype}.mat')
            loaded_data = load_mat_file(file_path, dtype)
            loaded_data_df = convert_to_dataframe(loaded_data, dtype, file_path if dtype == 'videoData' else None)

            if dtype == 'trialData':
                trialData = pd.concat([trialData, loaded_data_df], axis=0)
            elif dtype == 'sessionData':
                sessionData = pd.concat([sessionData, loaded_data_df], axis=0)
            elif dtype == 'spikeData':
                spikeData = pd.concat([spikeData, loaded_data_df], axis=0)
            elif dtype == 'videoData':
                videoData = pd.concat([videoData, loaded_data_df], axis=0)

    trialData.reset_index(inplace=True, drop=True)
    sessionData.reset_index(inplace=True, drop=True)
    spikeData.reset_index(inplace=True, drop=True)
    videoData.reset_index(inplace=True, drop=True)

    return trialData, sessionData, spikeData, videoData


# Function to assign group number based on visual orientation angle
def assign_group_visual(value):
    if value in [45, 49]:
        return "45-49"
    elif value in [135, 140]:
        return "135-140"
    elif value in [180, 185]:
        return "180-185"
    elif value in [225, 229, 230]:
        return "225-230"
    elif value in [270, 275]:
        return "270-275"
    else:  # For remaining values (315 and 319)
        return "315-319"


# Function to assign group number based on audio frequency value
def assign_group_auditory(value):
    if value in [8000, 8030]:
        return "8000-8030"
    elif value in [9000, 9020]:
        return "9000-9020"
    elif value in [10000, 10020, 10030]:
        return "10000-10030"
    elif value in [12000, 12030]:
        return "12000-12030"
    elif value in [13000, 13020]:
        return "13000-13020"
    else:  # For remaining values (315 and 319)
        return "14000-14030"


# Get an overview of the trial
def get_trial_counts(trialData):

    # Group the pairs or triples of stimuli together to
    # increase the number of trials per combination
    trialData['visGroupPreChange'] = trialData['visualOriPreChange'].apply(assign_group_visual)
    trialData['visGroupPostChange'] = trialData['visualOriPostChange'].apply(assign_group_visual)
    trialData['audioGroupPostChange'] = trialData['audioFreqPostChange'].apply(assign_group_auditory)
    trialData['audioGroupPreChange'] = trialData['audioFreqPreChange'].apply(assign_group_auditory)

    # Count the number of trials with each visual and auditory combination of stimuli
    groupDF = trialData.groupby(
        ['visGroupPreChange',
        'visGroupPostChange',
        'audioGroupPreChange',
        'audioGroupPostChange']
        ).size().reset_index(name='Count')

    beforeGroupDF = trialData.groupby(
        ['visGroupPreChange',
        'audioGroupPreChange']
        ).size().reset_index(name='Count')
    afterGroupDF = trialData.groupby(
        ['visGroupPostChange',
        'audioGroupPostChange']
        ).size().reset_index(name='Count')

    return groupDF, beforeGroupDF, afterGroupDF


# A function to extract only the neuron spikes in the duration of each trial
def get_trial_spikes(sessionDF, trialDF, spikeDF):
    newTrialDF = pd.DataFrame(columns=trialDF.columns)
    newTrialDF["neuronSpikes"] = ''
    newTrialDF["shortResponse"] = ''

    for session in sessionDF["session_ID"]:
        trialDF_ses = trialDF[trialDF["session_ID"] == session]
        spikeDF_ses = spikeDF[spikeDF["session_ID"] == session]
        trialSpikeData = []
        shortResponses = []

        for i, trial in trialDF_ses.iterrows():
            trial_start = trial["stimChange"] - 3000000
            trial_end_ts = trial["trialEnd"]
            trial_end_stim_ch = trial["stimChange"] + 1000000
            if trial_end_stim_ch <= trial_end_ts:
                trial_end = trial_end_stim_ch
                short_response = False
            else:
                trial_end = trial_end_ts
                short_response = True

            neuronSpikes = {}

            for j, neuron in spikeDF_ses.iterrows():
                ts = neuron["ts"]
                spikes_in_trial = ts[(ts >= trial_start) & (ts <= trial_end)]
                neuronSpikes[neuron["cell_ID"]] = spikes_in_trial

            print(len(neuronSpikes))
            trialID = trial["trialNum"]
            trialSpikeData.append(neuronSpikes)
            shortResponses.append(short_response)

        trialDF_ses["neuronSpikes"] = trialSpikeData
        trialDF_ses["shortResponse"] = shortResponses
        newTrialDF = pd.concat([newTrialDF, trialDF_ses], axis=0)

    return newTrialDF


def save_df_to_pickle(df, name, path):
    # Get the current date and time
    current_time = datetime.now()

    # Format the date and time in a filename-friendly format (e.g., 'YYYY-MM-DD_HH-MM-SS')
    formatted_time = current_time.strftime('%d-%m-%Y_%H-%M-%S')

    # Check if the save directory exists, and if not, create it
    if not os.path.exists(path):
        os.makedirs(path)

    # Define the filename with the current date and time
    filename = Path(f'{path}/{name}_{formatted_time}.pkl')

    # Save the DataFrame to a CSV file
    df.to_pickle(filename)
    print(f'DataFrame saved as {filename}')


def binarize_neurons_in_trial(trialData, interval):
    trialSpikeData = []
    print("Starting binarization of neuron firing spikes")

    # Iterate through each trial and get its start and end time
    # (or 1s after stim. change if the trial was longer)
    for index, trial in trialData.iterrows():
        start_time  = trial["stimChange"] - 2000000
        if trial["shortResponse"]:
            end_time = trial["trialEnd"]
        else:
            end_time = trial["stimChange"] + 1000000

        # Initialize the bin spikes dictionary
        bin_neuron_spikes = {}

        # Initialize the array of time bins
        intervals = np.arange(start_time, end_time, interval)
        print(end_time - start_time)

        for neuron, firing_timestamps in trial["neuronSpikes"].items():
            # Convert firing_timestamps to a NumPy array for efficient processing
            ts_array = np.array(firing_timestamps)

            # Use np.digitize to find the interval each timestamp falls into
            bins = np.digitize(ts_array, intervals)
            print(bins)

            # Initialize bin_series with 0 (indicating no firing)
            bin_series = np.full(len(intervals), 0)

            # Set to 1 if there's at least one spike in an interval
            bin_series[np.unique(bins) - 1] = 1  # -1 because np.digitize bin numbering starts from 1

            bin_neuron_spikes[neuron] = bin_series

        trialSpikeData.append(bin_neuron_spikes)
        print(f"Trial {trial['trialNum']} done")
        print(len(trial["neuronSpikes"]))

    trialData["binSpikes"] = trialSpikeData
    return trialData

def count_bin_spikes(trialData, interval):
    trialSpikeCounts = []

    # Iterate through each trial and get its start and end time
    # (or 1s after stim. change if the trial was longer)
    for index, trial in trialData.iterrows():
        start_time  = trial["stimChange"] - 2000000
        if trial["shortResponse"]:
            end_time = trial["trialEnd"]
        else:
            end_time = trial["stimChange"] + 1000000

        # Initialize the bin spikes dictionary
        bin_spike_counts = {}

        # Initialize the array of time bins
        intervals = np.arange(start_time, end_time, interval)

        for neuron, firing_timestamps in trial["neuronSpikes"].items():
            # Convert firing_timestamps to a NumPy array for efficient processing
            ts_array = np.array(firing_timestamps)

            # Use np.digitize to find the interval each timestamp falls into
            bins = np.digitize(ts_array, intervals)

            # Initialize count_series with 0
            count_series = np.full(len(intervals), 0)

            # Count the number of spikes in a time bin and add it to the count_series
            for spike in bins:
                count_series[spike-1] += 1

            bin_spike_counts[neuron] = count_series

        trialSpikeCounts.append(bin_spike_counts)
        # print(f"Trial {trial['trialNum']} done")

    # trialData[f"binSpikeCounts{int(interval/1000)}"] = trialSpikeCounts
    return trialSpikeCounts




########################################################################################################################################################################

# # Old functions for binarizing neuron firing in the entire sessions

# def binarize_neuron_firings(neuron_df, start_time, end_time, interval_duration):
#     """
#     Adds a column to the input DataFrame with binarized neuron firing data over specified intervals.

#     Parameters:
#     - neuron_df: pandas DataFrame, each row represents a neuron and contains a column 'ts' with firing timestamps.
#     - start_time: int, start time of the experiment in microseconds.
#     - end_time: int, end time of the experiment in microseconds.
#     - interval_duration: int, duration of each discrete time interval in microseconds.

#     Returns:
#     - pandas DataFrame, input DataFrame with an additional column 'binarized_intervals'.
#     """



#     # Function to binarize firing intervals for a single neuron
#     def binarize_intervals(firing_timestamps):
#         time_range = pd.date_range(start=pd.to_datetime(start_time, unit='us'),
#                                    end=pd.to_datetime(end_time, unit='us'),
#                                    freq=f'{interval_duration}us')
#         firing_times = pd.to_datetime(firing_timestamps, unit='us')
#         result = np.full(len(time_range) - 1, -1)
#         for i in range(len(time_range) - 1):
#             if any((firing_times >= time_range[i]) & (firing_times < time_range[i + 1])):
#                 result[i] = 1


#         print(f"neuron done")
#         return result

#     # Apply the binarize_intervals function to each row/neuron in the DataFrame
#     neuron_df['binarized_ts'] = neuron_df['ts'].apply(binarize_intervals)

#     return neuron_df



# def binarize_session_firings(session_df, neuron_df, interval_duration):
#     # Create the dataframe for the binarized data
#     newSpikeData = pd.DataFrame(columns=neuron_df.columns)

#     # Iterate through each session and binarize the data of neurons in that
#     # session, adding them to the new dataframe
#     for i,s in session_df.iterrows():
#         neurons = neuron_df[neuron_df["session_ID"] == s["session_ID"]]
#         newSpikeData = pd.concat([newSpikeData, binarize_neuron_firings(neurons, s["t_start"], s["t_stop"], interval_duration)], axis=0)

#     return newSpikeData


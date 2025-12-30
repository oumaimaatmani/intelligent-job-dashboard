def read_csv(file_path):
    import pandas as pd
    return pd.read_csv(file_path)

def write_csv(dataframe, file_path):
    import pandas as pd
    dataframe.to_csv(file_path, index=False)

def ensure_directory_exists(directory):
    import os
    if not os.path.exists(directory):
        os.makedirs(directory)

def get_file_path(directory, filename):
    import os
    return os.path.join(directory, filename)
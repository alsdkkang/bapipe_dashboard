import click

@click.group()
def cli():
    """Run commands from inside the project directory"""
    pass

@cli.group(chain=True)
def config():
    pass

@cli.group(chain=True)
def registration():
    pass

@registration.command()
def create():
    import pandas as pd
    from .gui.draw_registrations import registration_viewer
    df = pd.read_csv('datafiles.csv')
    registration_viewer(df.video.tolist())
    print('done')

@registration.command()
def calibrate():
    import pandas as pd

    def get_points(group):
        # swap axes so coordinates are x, y
        return group[['axis-2', 'axis-1']].values 

    datafiles_df = pd.read_csv('datafiles.csv', index_col='id')
    df = pd.read_csv('registration.csv')
    df['axis-0'] = df['axis-0'].astype(int) 
    g = df.groupby('axis-0')
    assert len(set(g.count().values.reshape(-1))) == 1
    out = g.apply(get_points)
    datafiles_df['registration'] = out.values
    datafiles_df.to_csv('datafiles.csv')
    print("updated datafiles.csv")

@registration.command()
@click.option('--plot', type=click.Choice(['scatter', 'line']), default='scatter', help='Scatter plot or line plot')
def visualize(scatter):
    import matplotlib.pyplot as plt
    import pandas as pd
    import numpy as np
    
    df = pd.read_csv('registration.csv')
    def get_points(group):
        return group[['axis-2', 'axis-1']].values # swap axes so coordinates are x, y

    g = df.groupby('axis-0')
    assert len(set(g.count().values.reshape(-1))) == 1
    out = g.apply(get_points)
    arr = np.stack(out).transpose(1, 2, 0)
    
    if scatter:
        plt.scatter(arr[0,0], arr[0,1])
        plt.scatter(arr[1,0], arr[1,1])
        plt.scatter(arr[2,0], arr[2,1])
        plt.scatter(arr[3,0], arr[3,1])
        plt.show()
    else:    
        fig = plt.figure()
        ax = plt.gca()
        plt.imshow(np.ones(shape=(540, 960, 3)))
        for row in arr.transpose(2, 0, 1):
            x, y = row.T
            plt.plot([*x, x[0]], [*y, y[0]])
            
    plt.show()

@config.command()
def generate():
    from ruamel.yaml import YAML
    
    template = """
    # Box shape in mm (width, height)
    box_shape:
    
    # Path to DLC Folder (ideally relative)
    dlc_folder:
    """
    yaml = YAML()
    cfg = yaml.load(template)
    with open('config.yaml', 'w') as fp:
        yaml.dump(cfg, fp)
        
@cli.command()
def create_project():
    import pandas as pd
    import cv2
    from tkinter import Tk
    from tkinter.filedialog import askopenfilenames
    from pathlib import Path
    
    Tk().withdraw()
    filenames = askopenfilenames()    
    cwd = Path('.').absolute()
    
    files = []
    for f in filenames:
        f = Path(f)
        video_path = f.relative_to(cwd)
        video_id = f.parts[-1].split('.')[0]
        cap = cv2.VideoCapture(str(video_path))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        
        files.append({
            'id': video_id,
            'video': video_path,
        })
        
    df = pd.DataFrame(files)
    df = df.set_index('id')
    
    outfile = Path('datafiles.csv')
    df.to_csv(outfile)
    print(f"Created project with {len(files)} videos at {outfile.absolute().parent}")
    
    
if __name__ == '__main__':
    cli()
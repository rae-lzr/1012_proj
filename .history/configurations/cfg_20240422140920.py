import os

class CFG:
    seed = 42
    input_dataset_path = os.path.join(os.path.expanduser('~'), '/scratch/zl5162/gemma1000.csv')
    output_dataset_path = os.path.join(os.path.expanduser('~'), '/scratch/zl5162/output')
    preset = "gemma_instruct_2b_en" # name of pretrained Gemma
    sequence_length = 512 # max size of input sequence for training
    batch_size = 64 # size of the input batch in training
    epochs = 1 # number of epochs to train
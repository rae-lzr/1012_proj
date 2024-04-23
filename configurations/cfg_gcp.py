import os
import argparse

parser = argparse.ArgumentParser(description='Process some integers.')
parser.add_argument('--input_file', type=str, default='gemma1000.csv',
                    help='The name of the input dataset')
parser.add_argument('--preset', type=str, default='gemma_instruct_2b_en',
                    help='Name of the pretrained Gemma model')
parser.add_argument('--sequence_length', type=int, default=512,
                    help='Maximum size of input sequence for training')
parser.add_argument('--batch_size', type=int, default=1,
                    help='Size of the input batch in training')
parser.add_argument('--epochs', type=int, default=1,
                    help='Number of epochs to train')


args = parser.parse_args()

class CFGGCP:
    seed = 42
    dataset_path = os.path.join(os.path.expanduser('~'), '/dataset_1012/')
    input_file_name = args.input_file
    input_dataset_path = os.path.join(dataset_path, input_file_name)
    preset = args.preset
    sequence_length = args.sequence_length
    batch_size = args.batch_size
    epochs = args.epochs
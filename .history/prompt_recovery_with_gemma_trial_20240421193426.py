import os
os.environ["KERAS_BACKEND"] = "jax" # you can also use tensorflow or torch
os.environ["XLA_PYTHON_CLIENT_MEM_FRACTION"] = "1.00" # avoid memory fragmentation on JAX backend.

import keras
import keras_nlp

import numpy as np
import pandas as pd
from tqdm.notebook import tqdm
tqdm.pandas() # progress bar for pandas

import plotly.graph_objs as go
import plotly.express as px
from IPython.display import display, Markdown

"""# Configuration"""

class CFG:
    seed = 42
    dataset_path = "/kaggle/input/llm-prompt-recovery"
    preset = "gemma_instruct_2b_en" # name of pretrained Gemma
    sequence_length = 512 # max size of input sequence for training
    batch_size = 1 # size of the input batch in training
    epochs = 1 # number of epochs to train

"""# Reproducibility
Sets value for random seed to produce similar result in each run.
"""

keras.utils.set_random_seed(CFG.seed)

"""# Data

No training data is provided in this competition; in other words, we can use any openly available datasets for this competition. In this notebook, we will use two external datasets that utilize the **Gemma 7B** model to transform texts using prompts.

**Data Format:**

These datasets includes:
- `original_text`: Input text/essay that needs to be transformed.
- `rewrite_prompt`: Prompt/Instruction that was used in the Gemma LM to transform `original_text`. This is also our **target** for this competition.
- `rewritten_text`: Output text that was generated by the Gemma model.
"""

# `LLM Prompt Recovery - Synthetic Datastore dataset` by @dschettler8845
df1 = pd.read_csv("/kaggle/input/llm-prompt-recovery-synthetic-datastore/gemma1000_w7b.csv")
df1 = df1[["original_text", "rewrite_prompt", "gemma_7b_rewritten_text_temp0"]]
df1 = df1.rename(columns={"gemma_7b_rewritten_text_temp0":"rewritten_text"})
df1.head(2)

# `3000 Rewritten texts - Prompt recovery Challenge` by @dipamc77
df2 = pd.read_csv("/kaggle/input/3000-rewritten-texts-prompt-recovery-challenge/prompts_0_500_wiki_first_para_3000.csv")
df2.head(2)

# Merge all datasets
df = pd.concat([df1, df2], axis=0)
df = df.sample(2000).reset_index(drop=True) # to reduce training time we are only using 2k samples
df.head(5)

"""# Prompt Engineering

Here's a simple prompt template we'll use to create instruction-response pairs from the `original_text`, `rewritten_text`, and `rewritten_prompt`:

```
Instruction:
Below, the `Original Text` passage has been rewritten/transformed/improved into `Rewritten Text` by the `Gemma 7b-it` LLM with a certain prompt/instruction. Your task is to carefully analyze the differences between the "Original Text" and "Rewritten Text", and try to infer the specific prompt or instruction that was likely given to the LLM to rewrite/transform/improve the text in this way.

Original Text:
...

Rewritten Text:
...

Response:
...
```

This template will help the model to follow instruction and respond accurately. You can explore more advanced prompt templates for better results.
"""

template = """Instruction:\nBelow, the `Original Text` passage has been rewritten/transformed/improved into `Rewritten Text` by the `Gemma 7b-it` LLM with a certain prompt/instruction. Your task is to carefully analyze the differences between the `Original Text` and `Rewritten Text`, and try to infer the specific prompt or instruction that was likely given to the LLM to rewrite/transform/improve the text in this way.\n\nOriginal Text:\n{original_text}\n\nRewriten Text:\n{rewritten_text}\n\nResponse:\n{rewrite_prompt}"""

template2 = """Instruction:\nBelow, the `Original Text` passage has been summarized/paraphrased/expanded/simplified into `Rewritten Text` by the `Gemma 7b-it` LLM with a certain prompt/instruction. Your task is to carefully analyze the differences between the `Original Text` and `Rewritten Text`, and try to infer the specific prompt or instruction that was likely given to the LLM to summarize/paraphrase/expand/simplify the text in this way.\n\nOriginal Text:\n{original_text}\n\nRewriten Text:\n{rewritten_text}\n\nResponse:\n{rewrite_prompt}"""

df["prompt"] = df.progress_apply(lambda row: template.format(original_text=row.original_text,
                                                             rewritten_text=row.rewritten_text,
                                                             rewrite_prompt=row.rewrite_prompt), axis=1)
data = df.prompt.tolist()

"""Let's examine a sample prompt. As the answers in our dataset are curated with **markdown** format, we will render the sample using `Markdown()` to properly visualize the formatting.

## Sample
"""

def colorize_text(text):
    for word, color in zip(["Instruction", "Original Text", "Rewriten Text", "Response"],
                           ["red", "yellow", "blue", "green"]):
        text = text.replace(f"{word}:", f"\n\n**<font color='{color}'>{word}:</font>**")
    return text

# Take a random sample
sample = data[10]

# Give colors to Instruction, Response and Category
sample = colorize_text(sample)

# Show sample in markdown
display(Markdown(sample))

"""# Modeling

<div align="center"><img src="https://i.ibb.co/Bqg9w3g/Gemma-Logo-no-background.png" width="300"></div>

**Gemma** is a collection of advanced open LLMs developed by **Google DeepMind** and other **Google teams**, derived from the same research and technology behind the **Gemini** models. They can be integrated into applications and run on various platforms including mobile devices and hosted services. Developers can customize Gemma models using tuning techniques to enhance their performance for specific tasks, offering more targeted and efficient generative AI solutions beyond text generation.

Gemma models are available in several sizes so we can build generative AI solutions based on your available computing resources, the capabilities you need, and where you want to run them.

| Parameters size | Tuned versions    | Intended platforms                 | Preset                 |
|-----------------|-------------------|------------------------------------|------------------------|
| 2B              | Pretrained        | Mobile devices and laptops         | `gemma_2b_en`          |
| 2B              | Instruction tuned | Mobile devices and laptops         | `gemma_instruct_2b_en` |
| 7B              | Pretrained        | Desktop computers and small servers| `gemma_7b_en`          |
| 7B              | Instruction tuned | Desktop computers and small servers| `gemma_instruct_7b_en` |

In this notebook, we will utilize the `Gemma 2b-it` model from KerasNLP's pretrained models to recover the prompt. We are using the "Instruction tuned" model instead of the "Pretrained" one because the test data was generated from an instruction-tuned Gemma model. Additionally, we will fine-tune our model using instruction-response pairs thus fine-tuning an instruction-tuned model will likely yield better results.

To explore other available models, you can simply adjust the `preset` value in the `CFG` (config). You can find a list of other pretrained models on the [KerasNLP website](https://keras.io/api/keras_nlp/models/).

## Gemma Causal LM

The code below will build an end-to-end Gemma model for causal language modeling (hence the name `GemmaCausalLM`). A causal language model (LM) predicts the next token based on previous tokens. This task setup can be used to train the model unsupervised on plain text input or to autoregressively generate plain text similar to the data used for training. This task can be used for pre-training or fine-tuning a Gemma model simply by calling `fit()`.

This model has a `generate()` method, which generates text based on a prompt. The generation strategy used is controlled by an additional sampler argument on `compile()`. You can recompile the model with different `keras_nlp.samplers` objects to control the generation. By default, `"greedy"` sampling will be used.

> The `from_preset` method instantiates the model from a preset architecture and weights.
"""

gemma_lm = keras_nlp.models.GemmaCausalLM.from_preset(CFG.preset)
gemma_lm.summary()

"""## Gemma LM Preprocessor

An important part of the Gemma model is the **Preprocessor** layer, which under the hood uses **Tokenizer**.

**What it does:** The preprocessor takes input strings and transforms them into a dictionary (`token_ids`, `padding_mask`) containing preprocessed tensors. This process starts with tokenization, where input strings are converted into sequences of token IDs.

**Why it's important:** Initially, raw text data is complex and challenging for modeling due to its high dimensionality. By converting text into a compact set of tokens, such as transforming `"The quick brown fox"` into `["the", "qu", "##ick", "br", "##own", "fox"]`, we simplify the data. Many models rely on special tokens and additional tensors to understand input. These tokens help divide input and identify padding, among other tasks. Making all sequences the same length through padding boosts computational efficiency, making subsequent steps smoother.

Explore the following pages to access the available preprocessing and tokenizer layers in **KerasNLP**:
- [Preprocessing](https://keras.io/api/keras_nlp/preprocessing_layers/)
- [Tokenizers](https://keras.io/api/keras_nlp/tokenizers/)
"""

x, y, sample_weight = gemma_lm.preprocessor(data[0:2])

"""This preprocessing layer will take in batches of strings, and return outputs in a `(x, y, sample_weight)` format, where the `y` label is the next token id in the `x` sequence.

From the code below, we can see that, after the preprocessor, the data shape is `(num_samples, sequence_length)`.
"""

# Display the shape of each processed output
for k, v in x.items():
    print(k, ":", v.shape)

"""# Inference before Fine-Tuning

Before we do fine-tuning, let's try to recover the prompt using the Gemma model with some prepared prompts and see how it responds.

> As this model is not yet fine-tuned for instruction, you will notice that the model's responses are inaccurate.

## Sample 1
"""

# Take one sample
row = df.iloc[10]

# Generate Prompt using template
prompt = template.format(
    original_text=row.original_text,
    rewritten_text=row.rewritten_text,
    rewrite_prompt="",
)

# Infer
output = gemma_lm.generate(prompt, max_length=512)

# Colorize
output = colorize_text(output)

# Display in markdown
display(Markdown(output))

"""## Sample 2"""

# Take one sample
row = df.iloc[20]

# Generate Prompt using template
prompt = template.format(
    original_text=row.original_text,
    rewritten_text=row.rewritten_text,
    rewrite_prompt="",
)

# Infer
output = gemma_lm.generate(prompt, max_length=512)

# Colorize
output = colorize_text(output)

# Display in markdown
display(Markdown(output))

"""# Fine-tuning with LoRA

To get better responses from the model, we will fine-tune the model with Low Rank Adaptation (LoRA).

**What exactly is LoRA?**

LoRA is a method used to fine-tune large language models (LLMs) in an efficient way. It involves freezing the weights of the LLM and injecting trainable rank-decomposition matrices.

Imagine in an LLM, we have a pre-trained dense layer, represented by a $d \times d$ weight matrix, denoted as $W_0$. We then initialize two additional dense layers, labeled as $A$ and $B$, with shapes $d \times r$ and $r \times d$, respectively. Here, $r$ denotes the rank, which is typically **much smaller than** $d$. Prior to LoRA, the model's output was computed using the equation $output = W_0 \cdot x + b_0$, where $x$ represents the input and $b_0$ denotes the bias term associated with the original dense layer, which remains frozen. After applying LoRA, the equation becomes $output = (W_0 \cdot x + b_0) + (B \cdot A \cdot x)$, where $A$ and $B$ denote the trainable rank-decomposition matrices that have been introduced.

<center><img src="https://i.ibb.co/DWsbhLg/LoRA.png" width="300"><br/>
Credit: <a href="https://arxiv.org/abs/2106.09685">LoRA: Low-Rank Adaptation of Large Language Models</a> Paper</center>


In the LoRA paper, $A$ is initialized with $\mathcal{N} (0, \sigma^2)$ and $B$ with $0$, where $\mathcal{N}$ denotes the normal distribution, and $\sigma^2$ is the variance.

**Why does LoRA save memory?**

Even though we're adding more layers to the model with LoRA, it actually helps save memory. This is because the smaller layers (A and B) have fewer parameters to learn compared to the big model and fewer trainable parameters mean fewer optimizer variables to store. So, even though the overall model might seem bigger, it's actually more efficient in terms of memory usage.

> This notebook uses a LoRA rank of `4`. A higher rank means more detailed changes are possible, but also means more trainable parameters.
"""

# Enable LoRA for the model and set the LoRA rank to 4.
gemma_lm.backbone.enable_lora(rank=4)
gemma_lm.summary()

"""**Notice** that, the number of trainable parameters is reduced from ~$2.5$ billions to ~$1.3$ millions after enabling LoRA.

## Training
"""

# Limit the input sequence length to 512 (to control memory usage).
gemma_lm.preprocessor.sequence_length = CFG.sequence_length

# Compile the model with loss, optimizer, and metric
gemma_lm.compile(
    loss=keras.losses.SparseCategoricalCrossentropy(from_logits=True),
    optimizer=keras.optimizers.Adam(learning_rate=3e-5),
    weighted_metrics=[keras.metrics.SparseCategoricalAccuracy()],
)

# Train model
gemma_lm.fit(data, epochs=CFG.epochs, batch_size=CFG.batch_size)

"""# Inference after fine-tuning

Let's see how our fine-tuned model responds to the same questions we asked before fine-tuning the model.

## Sample 1
"""

# Take one sample
row = df.iloc[10]

# Generate Prompt using template
prompt = template.format(
    original_text=row.original_text,
    rewritten_text=row.rewritten_text,
    rewrite_prompt="",
)

# Infer
output = gemma_lm.generate(prompt, max_length=512)

# Colorize
output = colorize_text(output)

# Display in markdown
display(Markdown(output))

"""## Sample 2"""

# Take one sample
row = df.iloc[20]

# Generate Prompt using template
prompt = template.format(
    original_text=row.original_text,
    rewritten_text=row.rewritten_text,
    rewrite_prompt="",
)

# Infer
output = gemma_lm.generate(prompt, max_length=512)

# Colorize
output = colorize_text(output)

# Display in markdown
display(Markdown(output))

"""# Test Data"""

test_df = pd.read_csv("/kaggle/input/llm-prompt-recovery/test.csv")
test_df['original_text'] = test_df['original_text'].fillna("")
test_df['rewritten_text'] = test_df['rewritten_text'].fillna("")
test_df.head()

"""## Test Sample

Now, let's try out a sample from test data that model hasn't seen during training.
"""

row = test_df.iloc[0]

# Generate Prompt using template
prompt = template.format(
    original_text=row.original_text,
    rewritten_text=row.rewritten_text,
    rewrite_prompt="",
)

# Infer
output = gemma_lm.generate(prompt, max_length=512)

# Colorize
output = colorize_text(output)

# Display in markdown
display(Markdown(output))

"""# Submission"""

preds = []
for i in tqdm(range(len(test_df))):
    row = test_df.iloc[i]

    # Generate Prompt using template
    prompt = template.format(
        original_text=row.original_text,
        rewritten_text=row.rewritten_text,
        rewrite_prompt=""
    )

    # Infer
    output = gemma_lm.generate(prompt, max_length=512)
    pred = output.replace(prompt, "") # remove the prompt from output

    # Store predictions
    preds.append([row.id, pred])

"""While preparing the submission file, we must keep in mind that, leaving any `rewrite_prompt` blank as null answers will throw an error."""

sub_df = pd.DataFrame(preds, columns=["id", "rewrite_prompt"])
sub_df['rewrite_prompt'] = sub_df['rewrite_prompt'].fillna("")
sub_df['rewrite_prompt'] = sub_df['rewrite_prompt'].map(lambda x: "Improve the essay" if len(x) == 0 else x)
sub_df.to_csv("submission.csv",index=False)
sub_df.head()

"""# Conclusion

The result is pretty good. Still there is ample room for improvement. Here are some tips to improve performance:

- Try using the larger version of **Gemma** (7B).
- Increase `sequence_length`.
- Experiment with advanced prompt engineering techniques.
- Implement augmentation to increase the number of samples.
- Utilize a learning rate scheduler.

# Reference
* [Fine-tune Gemma models in Keras using LoRA](https://www.kaggle.com/code/nilaychauhan/fine-tune-gemma-models-in-keras-using-lora)
* [Parameter-efficient fine-tuning of GPT-2 with LoRA](https://keras.io/examples/nlp/parameter_efficient_finetuning_of_gpt2_with_lora/)
* [Gemma - KerasNLP](https://keras.io/api/keras_nlp/models/gemma/)
"""
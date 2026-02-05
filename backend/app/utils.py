import re
from collections import Counter

import polars as pl
import matplotlib.pyplot as plt
from wordcloud import WordCloud, STOPWORDS

def wordcloud(df, column="grievance", 
                custom_stopwords=[]):
    """
    Minimal word cloud from a Polars DataFrame column.
    """

    # Pull text column (works for DataFrame or LazyFrame)
    if isinstance(df, pl.LazyFrame):
        texts = df.select(column).collect().get_column(column).to_list()
    else:
        texts = df.get_column(column).to_list()

    # Join corpus
    text = " ".join(t for t in texts if isinstance(t, str)).lower()

    # Light normalization
    text = re.sub(r"http\S+|www\.\S+", " ", text)
    text = re.sub(r"\d+", " ", text)
    text = re.sub(r"[^a-z\s]+", " ", text)

    # Stopwords
    custom_stopwords = set(custom_stopwords).union(
        set(["odisha", "sir", "request", "kindly", "regarding", "please", "give", "madam", "need", "take"])
    )
    stopwords = set(STOPWORDS).union(custom_stopwords)

    words = [
        w for w in text.split()
        if len(w) > 2 and w not in stopwords
    ]

    freqs = Counter(words)

    wc = WordCloud(
        width=1600,
        height=900,
        background_color="white",
        collocations=False,
    ).generate_from_frequencies(freqs)

    plt.figure(figsize=(10, 6))
    plt.imshow(wc, interpolation="bilinear")
    plt.axis("off")
    plt.show()

    return wc

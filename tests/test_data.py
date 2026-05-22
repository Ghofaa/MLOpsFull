import pandas as pd

from madewithml import data


def test_clean_text_lowercases_removes_stopwords_and_punctuation():
    text = data.clean_text("This is a GREAT project, with BERT!!!")

    assert text == "great project bert"


def test_preprocess_returns_tokenized_arrays(monkeypatch):
    def fake_tokenize(batch):
        return {
            "ids": [[101, 102]],
            "masks": [[1, 1]],
            "targets": batch["tag"].to_numpy(),
        }

    monkeypatch.setattr(data, "tokenize", fake_tokenize)
    df = pd.DataFrame(
        [
            {
                "id": 1,
                "created_on": "2026-05-14",
                "title": "BERT Classifier",
                "description": "NLP project",
                "tag": "natural-language-processing",
            }
        ]
    )

    outputs = data.preprocess(df, class_to_index={"natural-language-processing": 0})

    assert outputs["ids"] == [[101, 102]]
    assert outputs["masks"] == [[1, 1]]
    assert outputs["targets"].tolist() == [0]

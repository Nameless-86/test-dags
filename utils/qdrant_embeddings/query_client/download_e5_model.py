from transformers import AutoTokenizer, AutoModel

AutoTokenizer.from_pretrained("intfloat/e5-large-v2").save_pretrained(
    "./local_e5_model"
)
AutoModel.from_pretrained("intfloat/e5-large-v2").save_pretrained("./local_e5_model")

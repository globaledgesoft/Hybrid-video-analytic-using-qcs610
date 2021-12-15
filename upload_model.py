import boto3
import json

config_file = open('config.json')
config = json.load(config_file)

s3 = boto3.client('s3',region_name=config["aws_region"], aws_access_key_id=config["aws_accesskey"], aws_secret_access_key=config["aws_secretekey"])
s3.upload_file( "./assets/version-RFB-320.onnx", config['in_bucket'], "version-RFB-320.onnx")         # FACE DETECTION MODEL
s3.upload_file( "./assets/emotion-ferplus-7.onnx", config['in_bucket'], "emotion-ferplus-7.onnx")     # EMOTION RECONIZER
s3.upload_file( "./assets/arial.ttf", config['in_bucket'], "arial.ttf")   


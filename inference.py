import qcsnpe as qc
import cv2
import numpy as np
import json
import sys
sys.path.append('boto3')
from datetime import datetime, timedelta
import time
import boto3


config_file = open('config.json')
config = json.load(config_file)

def postprocess(out, video_height, video_width):
    boxes = out["Postprocessor/BatchMultiClassNonMaxSuppression_boxes"]
    scores = out["Postprocessor/BatchMultiClassNonMaxSuppression_scores"]
    classes = out["detection_classes:0"]
    found = []

    for cur in range(len(scores)):
        probability = scores[cur]
        class_index = int(classes[cur])
        if class_index != 1 or probability < 0.6:    # checking person detection
            continue

        y1 = int(boxes[4 * cur] * video_height)
        x1 = int(boxes[4 * cur + 1] * video_width)
        y2 = int(boxes[4 * cur + 2] * video_height)
        x2 = int(boxes[4 * cur + 3] * video_width)
        found.append([(x1, y1), (x2, y2)])
    return found

def main_stream():
    s3 = boto3.resource("s3",region_name=config["aws_region"], aws_access_key_id=config["aws_accesskey"], aws_secret_access_key=config["aws_secretekey"])
    cap = cv2.VideoCapture(config['camera_pipeline'], cv2.CAP_GSTREAMER)
    out_layers = np.array(["Postprocessor/BatchMultiClassNonMaxSuppression", "add_6"])
    model_path = config['model_path']
    dlc = qc.qcsnpe(model_path,out_layers, 0)
    count = 0;
    i=0
    
    while(cap.isOpened()):
        ret, image = cap.read()
        if image is None:
            break
        img = cv2.resize(image, (300,300))
        out = dlc.predict(img)
        people_cord = []
        res = postprocess(out, image.shape[0], image.shape[1])
        if(count <= 0):
            count = 0 
        else:
            count = count -1
 
        if (len(res) and (count == 0)):
            print("number of people: ", len(res))
            starttime = datetime.now() - timedelta(seconds=5) 
            endtime =  starttime + timedelta(seconds=2) 
            timestamp ={
                "ST" : str(starttime),
                "ET" : str(endtime),
                "Number" : len(res)
            }
            json_object = json.dumps(timestamp, indent = 3)
  
            with open(config['filename'], 'w') as f:
                f.write(json_object)
            count = 50
            i=i+1
            s3.meta.client.upload_file(config['filename'], config['in_bucket'], 'timestamp.json')

    if(cap):
        cap.release()


if __name__ == '__main__':
        main_stream()
   

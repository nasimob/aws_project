import flask
from flask import request
import os
from bot import ObjectDetectionBot
from loguru import logger
import json
import boto3
from botocore.exceptions import ClientError


def get_secret():
    secret_name = "polybot/telegram_token"
    region_name = "eu-north-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        logger.error(e)
        return False
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return False
    except KeyError:
        print("Key 'TELEGRAM_TOKEN' not found in the JSON data")
        return False

    secret = get_secret_value_response['SecretString']
    secret_dict = json.loads(secret)
    telegram_token = secret_dict["TELEGRAM_TOKEN"]

    return  telegram_token

app = flask.Flask(__name__)


# TODO load TELEGRAM_TOKEN value from Secret Manager
TELEGRAM_TOKEN = get_secret()

TELEGRAM_APP_URL = os.environ['TELEGRAM_APP_URL']


@app.route('/', methods=['GET'])
def index():
    return 'Ok'


@app.route(f'/{TELEGRAM_TOKEN}/', methods=['POST'])
def webhook():
    req = request.get_json()
    bot.handle_message(req['message'])
    return 'Ok'


@app.route(f'/results/', methods=['GET'])
def results():
    prediction_id = request.args.get('predictionId')

    # TODO use the prediction_id to retrieve results from DynamoDB and send to the end-user
    prediction_summary = bot.get_item_by_prediction_id(prediction_id)
    logger.info(f'prediction_summary in results: {prediction_summary}')
    logger.info(f'type: {type(prediction_summary)}')
    chat_id = prediction_summary['chat_id']
    logger.info(f'chat id: {chat_id}')
    text_results = bot.handle_dynamo_message(prediction_summary)
    bot.send_text(chat_id, text_results)
    return 'Ok'


@app.route(f'/loadTest/', methods=['POST'])
def load_test():
    req = request.get_json()
    bot.handle_message(req['message'])
    return 'Ok'

@app.route('/health')
def health_check():
    return 'OK', 200

if __name__ == "__main__":
    bot = ObjectDetectionBot(TELEGRAM_TOKEN, TELEGRAM_APP_URL)

    app.run(host='0.0.0.0', port=8443)

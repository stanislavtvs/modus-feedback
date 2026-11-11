import json

def approved_post(client,url,data=None,hide=True):
    data=data or {}
    response=client.post(url,json.dumps(data),content_type='application/json')
    if response.status_code==409 and 'preview' in response.json():
        data=dict(data,privacy_token=response.json()['privacy_token'],hide_sensitive=hide)
        return client.post(url,json.dumps(data),content_type='application/json')
    return response

import requests
from gidra.proxy import StarRailProxy
from bottle import route, run, request
from gidra.proto import Gateserver
import base64

PROXY_GATEWAY = ('127.0.0.1', 8888)

TARGET_DISPATCH_URL = 'https://127.0.0.1/query_gateway'
TARGET_GATEWAY = ('127.0.0.1', 22102)

@route('/query_gateway')
def handle_query_gateway():
    # Trick to bypass system proxy.
    session = requests.Session()
    session.trust_env = False

    r = session.get(f'{TARGET_DISPATCH_URL}?{request.query_string}')

    proto = Gateserver()
    proto.parse(base64.b64decode(r.text))

    if proto.retcode == 0:
        proto.ip, proto.port = PROXY_GATEWAY

    return base64.b64encode(bytes(proto)).decode()

proxy = StarRailProxy(PROXY_GATEWAY, TARGET_GATEWAY)

def main():
    proxy.start()
    run(host='127.0.0.1', port=8081, debug=False)

if __name__ == '__main__':
    main()

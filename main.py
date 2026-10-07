"""A06 web demo and optional CLI evidence."""
import argparse,json
from bootstrap import build_services
from presentation.search_ui import create_app as web_app

def create_app(services=None,testing=False):return web_app(services or build_services(),testing)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=5000)
    parser.add_argument('--demo',action='store_true');parser.add_argument('--output',default='demo-results.json')
    args=parser.parse_args()
    services=build_services()
    if args.demo:
        result=[services.search(query,top_k=5) for query in ['quick drying water shoes','giày đi nước màu đen dưới 8 trăm']]
        with open(args.output,'w',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    else:web_app(services).run(host='127.0.0.1',port=args.port,debug=False)

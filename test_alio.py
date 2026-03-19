import requests

resp = requests.get(
    'https://www.work.go.kr/opi/opi/empInfo/empInfoSrch/list/dtlEmpSrchList.do',
    params={
        'callTp': 'L',
        'returnType': 'JSON',
        'empTpGbCd': '1',
        'keywd': '공공기관',
        'pageIndex': 1,
        'pageUnit': 20,
    },
    headers={'User-Agent': 'Mozilla/5.0'},
    timeout=15
)
print(resp.status_code)
print(resp.text[:1000])
import requests

headers = {
    'Accept': '*/*',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Accept-Language': 'en-US,en;q=0.6',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Content-Length': '929',
    'Host': 'mnrwefss2q-dsn.algolia.net',
    'Origin': 'https://www.grailed.com',
    'Pragma': 'no-cache',
    'Referer': 'https://www.grailed.com/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'cross-site',
    'Sec-GPC': '1',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
    'content-type': 'application/x-www-form-urlencoded',
    'sec-ch-ua': '"Brave";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'x-algolia-api-key': 'c89dbaddf15fe70e1941a109bf7c2a3d',
    'x-algolia-application-id': 'MNRWEFSS2Q'
}

payload = {
    "requests":[
        {
            "indexName":"Listing_by_listing_quality_production",
            "params":"analytics=true&clickAnalytics=true&enableABTest=true&facets=%5B%22badges%22%2C%22category_path%22%2C%22category_size%22%2C%22color%22%2C%22condition%22%2C%22department%22%2C%22designers.name%22%2C%22location%22%2C%22price_i%22%2C%22strata%22%5D&getRankingInfo=true&highlightPostTag=__%2Fais-highlight__&highlightPreTag=__ais-highlight__&hitsPerPage=40&maxValuesPerFacet=165&numericFilters=%5B%22price_i%3E%3D0%22%2C%22price_i%3C%3D1000000%22%5D&page=0&query=dior%20gat&userToken=c9797a1d-ce45-4aab-8dc0-4b71c0e0f0d0"
        },
        {
            "indexName":"Listing_by_listing_quality_production",
            "params":"analytics=false&clickAnalytics=false&enableABTest=true&facets=price_i&getRankingInfo=true&highlightPostTag=__%2Fais-highlight__&highlightPreTag=__ais-highlight__&hitsPerPage=0&maxValuesPerFacet=165&page=0&query=dior%20gat&userToken=c9797a1d-ce45-4aab-8dc0-4b71c0e0f0d0"
        }
    ]
}

session = requests.Session()
session.headers.update(headers)

response = session.post('https://mnrwefss2q-dsn.algolia.net/1/indexes/*/queries?x-algolia-agent=Algolia%20for%20JavaScript%20(4.14.3)%3B%20Browser%3B%20instantsearch.js%20(4.75.5)%3B%20react%20(18.2.0)%3B%20react-instantsearch%20(7.13.8)%3B%20react-instantsearch-core%20(7.13.8)%3B%20next.js%20(14.2.33)%3B%20JS%20Helper%20(3.22.5)', json=payload)

print(response.status_code)
print(response.json())

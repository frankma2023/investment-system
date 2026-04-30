## 指数K线数据API

### 简要描述:
`获取K线数据。`

### 说明:
`中证指数全收益率2016年以前没有数据。`

### 请求URL:
`https://open.lixinger.com/api/cn/index/candlestick`

### Url For Vibe Coding:
`https://www.lixinger.com/api/open-api/html-doc/cn/index/candlestick`

### 请求方式:
`POST`

### 参数:

| 参数名称 | 必选 | 数据类型 | 说明 |
| --- | --- | --- | --- |
| token | Yes | String | 我的Token页有用户专属且唯一的Token。 |
| stockCode | Yes | String | 请参考[指数信息API](https://open.lixinger.com/api/cn/index/candlestick)获取合法的stockCode。stockCode仅在请求数据为date range的情况下生效。 |
| type | Yes | String | 收盘点位类型，例如，“normal”。<br>当前支持：<br>• 正常点位: normal<br>• 全收益率点位: total_return |
| date | No | String: YYYY-MM-DD (北京时间) | 信息日期。用于获取指定日期数据。 |
| startDate | No | String: YYYY-MM-DD (北京时间) | 信息起始时间。用于获取一定时间范围内的数据，开始和结束的时间间隔不超过10年。 |
| endDate | No | String: YYYY-MM-DD (北京时间) | 信息结束时间。用于获取一定时间范围内的数据。默认值是上周一。 |
| limit | No | Number | 返回最近数据的数量。 |

### 返回数据

| 参数名称 | 数据类型 | 说明 |
| :--- | :--- | :--- |
| date | Date | 数据时间 |
| open | Number | 开盘价 |
| close | Number | 收盘价 |
| high | Number | 最高价 |
| low | Number | 最低价 |
| volume | Number | 成交量 |
| amount | Number | 金额 |
| change | Number | 涨跌幅 |

### 使用示例
获取数据
{
	"token": "2fff120c-4525-425b-98f7-0ace855b8326",
	"type": "normal",
	"startDate": "2026-03-10",
	"endDate": "2026-03-17",
	"stockCode": "000016"
}

返回数据
{
  "code": 1,
  "message": "success",
  "data": [
    {
      "date": "2026-03-16T00:00:00+08:00",
      "volume": 5959600000,
      "open": 2952.42,
      "high": 2955,
      "low": 2927.94,
      "close": 2954.09,
      "change": -0.0009,
      "amount": 143862000000
    },
    {
      "date": "2026-03-13T00:00:00+08:00",
      "volume": 6863300000,
      "open": 2961.73,
      "high": 2977.84,
      "low": 2951.7,
      "close": 2956.85,
      "change": -0.005,
      "amount": 134239000000
    },
    {
      "date": "2026-03-12T00:00:00+08:00",
      "volume": 5564410000,
      "open": 2978.12,
      "high": 2985.55,
      "low": 2954.3,
      "close": 2971.56,
      "change": -0.0046,
      "amount": 125465000000
    },
    {
      "date": "2026-03-11T00:00:00+08:00",
      "volume": 5603200000,
      "open": 2983.46,
      "high": 2988.75,
      "low": 2970.83,
      "close": 2985.34,
      "change": 0.0012,
      "amount": 122447000000
    },
    {
      "date": "2026-03-10T00:00:00+08:00",
      "volume": 5422690000,
      "open": 2973.82,
      "high": 2985.31,
      "low": 2969.91,
      "close": 2981.84,
      "change": 0.0064,
      "amount": 121762000000
    }
  ]
}

---
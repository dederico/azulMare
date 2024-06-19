const areaChartData = {
  labels  : [],
  title: 'Past Call Stats',
  datasets: []
};

const areaChartOptions = {
  maintainAspectRatio : false,
  responsive : true,
  legend: {
    display: true
  },
  scales: {
    xAxes: [{
      gridLines : {
        display : true,
      }
    }],
    yAxes: [{
      gridLines : {
        display : true,
      }
    }]
  }
}

const lineChartCanvas = $('#trendChart').get(0).getContext('2d')
const lineChartOptions = jQuery.extend(true, {}, areaChartOptions)
const lineChartData = jQuery.extend(true, {}, areaChartData)
lineChartOptions.datasetFill = false

const trendChart = new Chart(lineChartCanvas, { 
  type: 'line',
  data: lineChartData, 
  options: lineChartOptions
});

function getDataset(element) {
  const r = Math.floor(Math.random() * 256);
  const g = Math.floor(Math.random() * 256);
  const b = Math.floor(Math.random() * 256);
  return {
      label               : element.name,
      backgroundColor     : `rgba(${r},${g},${b},0.9)`,
      borderColor         : `rgba(${r},${g},${b},0.8)`,
      pointRadius         : false,
      pointColor          : '#3b8bba',
      pointStrokeColor    : `rgba(${r},${g},${b},1)`,
      pointHighlightFill  : '#fff',
      fill                : false,
      pointHighlightStroke: `rgba(${r},${g},${b},1)`,
      data                : [ element.ping ]
  }
}

function addTrendChart(response)
{
    trendChart.data.labels.push("10");

    if (trendChart.data.datasets.length == 0)
    {
        trendChart.data.datasets.push(getDataset({ name: "test", "ping": "35" }));
    }
    else
    {
        //pings.forEach(element => {
        //const matchingDataset = trendChart.data.datasets.find(dataset => dataset.label === element.name);

        //if (matchingDataset)
        //    matchingDataset.data.push(element.ping);
        //});
    }

    trendChart.update();
}


function getRandomColor(a = 1) {
    const r = Math.floor(Math.random() * 256);
    const g = Math.floor(Math.random() * 256);
    const b = Math.floor(Math.random() * 256);
    return `rgba(${r},${g},${b}, ${a})`;
  }

  function getDataset(element) {
    const col = getRandomColor(0.9);
    return {
      label: element.type,
      backgroundColor: col,
      borderColor: col,
      pointRadius: false,
      pointColor: '#3b8bba',
      pointStrokeColor: col,
      pointHighlightFill: '#fff',
      fill: false,
      pointHighlightStroke: col,
      data: element.records.reduce((acc, obj) => { acc.push(obj.totalCalls); return acc; }, [])
    }
  }

  const areaChartData = {
    labels: callsData[0].records.reduce((acc, obj) => { acc.push(obj.callDate); return acc; }, []),
    title: 'Past Call Stats',
    datasets: callsData.map(x => getDataset(x))
  };

  const barChartData = {
    labels: callsData[0].records.reduce((acc, obj) => { acc.push(obj.callDate); return acc; }, []),
    title: 'Past Call Stats',
    datasets: callsData.map(x => ({
      label: x.type,
      data: x.records.reduce((acc, obj) => { acc.push(obj.totalCalls); return acc; }, []),
      backgroundColor: getRandomColor(),
    }))
  };

  const doughnutChartData = {
    labels: callsData.reduce((acc, obj) => { acc.push(obj.type); return acc; }, []),
    datasets: [{
      label: 'Calls Highlight of Last 7 Days',
      data: callsData.reduce((acc, obj) => { const total = obj.records.reduce((t, i) => t + i.totalCalls, 0); acc.push(total); return acc; }, []),
      backgroundColor: [
        getRandomColor(),
        getRandomColor(),
        getRandomColor()
      ],
      hoverOffset: 4
    }]
  };

  const lineChartCanvas = $('#trendChart').get(0).getContext('2d')
  const doughnutChartCanvas = $('#doughnutChart').get(0).getContext('2d')
  const barChartCanvas = $('#barChart').get(0).getContext('2d')

  const trendChart = new Chart(lineChartCanvas, {
    type: 'line',
    data: areaChartData,
    options: {
      datasetFill: false,
      maintainAspectRatio: false,
      responsive: true,
      legend: {
        display: true
      },
      scales: {
        xAxes: [{
          gridLines: {
            display: true,
          }
        }],
        yAxes: [{
          gridLines: {
            display: true,
          }
        }]
      }
    }
  });

  const doughnutChart = new Chart(doughnutChartCanvas, {
    type: 'doughnut',
    data: doughnutChartData
  });

  const barChart = new Chart(barChartCanvas, {
    type: 'bar',
    data: barChartData,
    options: {
      scales: {
        xAxes: [{
          stacked: true
        }],
        yAxes: [{
          stacked: true
        }]
      },
      maintainAspectRatio: false
    }
  });

  $('#days').on('change', function (e) {
      const optionSelected = $("option:selected", this);
      window.location.href="/admin/dashboard?days=" + optionSelected.val();
  });

  const urlParams = new URLSearchParams(window.location.search);
  if(urlParams.has("days"))
    $("#days").val(urlParams.get("days"));
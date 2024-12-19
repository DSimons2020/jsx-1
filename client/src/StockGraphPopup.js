import React from 'react';
import { Line } from 'react-chartjs-2';
import './StockGraphPopup.css';
import { Chart, registerables } from 'chart.js';
Chart.register(...registerables);

const StockGraphPopup = ({ stockName, data, onClose }) => {
  const years = Array.from({ length: 2025 - 1899 + 1 }, (_, i) => i + 1899);  // Generate years from 1899 to 2025
  const prices = years.map(year => {
    const entry = data.find(d => d.year === year);
    return entry ? entry.price : null;  // Return price if exists, otherwise null
  });

  const chartData = {
    labels: years,
    datasets: [
      {
        label: `Value of ${stockName}`,
        data: prices,
        fill: false,
        borderColor: 'rgba(29,135,6,1)',
        tension: 0.001,
        spanGaps: true,  // Allow gaps in the line for null values
        pointStyle: 'rectRounded',
        pointRadius: 2,
      },
    ],
  };

  const chartOptions = {
    scales: {
      x: {
        type: 'linear',
        position: 'bottom',
        title: {
          display: true,
          text: 'Year',
        },
        ticks: {
          callback: function(value, index, values) {
            return value.toString();  // Display year without commas
          }
        },
        min: 1900, // Force the x-axis to start at 1900
      },
      y: {
        title: {
          display: true,
          text: 'Price (£)',
        },
        beginAtZero: true  // Ensure Y-axis starts at 0
      },
    },
  };

  return (
    <div className="popup-overlay">
      <div className="popup-content">
        <button className="close-button" onClick={onClose}>×</button>
        <Line data={chartData} options={chartOptions} />
      </div>
    </div>
  );
};

export default StockGraphPopup;

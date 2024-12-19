import React, { useEffect, useState } from 'react';
import './Ticker.css';

const Ticker = () => {
  const [alerts, setAlerts] = useState([]);

  useEffect(() => {
    const fetchWatchListAndStocks = async () => {
      const token = localStorage.getItem('token');

      try {
        const watchListResponse = await fetch('/api/watch_list', {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        });
        const watchList = await watchListResponse.json();

        const stocksResponse = await fetch('/api/stocks_with_history', {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        });
        const stocksData = await stocksResponse.json();

        const newAlerts = [];

        watchList.forEach(watchItem => {
          const stock = stocksData.find(stock => stock.stock_id === watchItem.stock_id);
          if (stock) {
            // Check for birth alert
            if (watchItem.birthAlert && stock.price === 8 && stock.previousPrice === 0) {
              newAlerts.push(`Birth! ${stock.name} has been born and is now available to buy`);
            }
            // Check for value alert
            if (watchItem.valueAlertEnabled && stock.price >= watchItem.valueAlert) {
              newAlerts.push(`Alert! ${stock.name} is valued at or above ${watchItem.valueAlert}!`);
            }
          }
        });

        setAlerts(newAlerts);

      } catch (error) {
        console.error("Error fetching data:", error);
      }
    };

    fetchWatchListAndStocks();

    const interval = setInterval(fetchWatchListAndStocks, 3000); // Check every 3 seconds for more frequent updates
    return () => clearInterval(interval); // Clean up on component unmount
  }, []);

  return (
    <div className="ticker-bar">
      <div className="ticker-text">
        {alerts.length > 0 ? alerts.join(' | ') : 'No alerts at this time | Set alerts for when stocks are born or when stocks reach a desired value on the Watch List page'}
      </div>
    </div>
  );
};

export default Ticker;

import React, { useEffect, useState } from 'react';
import './WatchList.css';

const WatchList = () => {
  const [categories, setCategories] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState('');
  const [stocksData, setStocksData] = useState([]); // Stores the stock data for the selected category

  // Fetch categories on component mount
  useEffect(() => {
    fetch('/api/categories')
      .then((response) => response.json())
      .then((data) => setCategories(data))
      .catch((error) => console.error('Error fetching categories:', error));
  }, []);

  // Fetch stocks for the selected category
  const handleCategoryChange = (event) => {
    const category = event.target.value;
    setSelectedCategory(category);

    if (category) {
      fetch(`/api/stocks/${category}`)
        .then((response) => response.json())
        .then((data) => setStocksData(data))
        .catch((error) => console.error('Error fetching stocks:', error));
    } else {
      setStocksData([]); // Reset stocksData if no category is selected
    }
  };

  // Update watchlist for a stock
  const postWatchListUpdate = (stockId, birthAlert, valueAlert, valueAlertEnabled) => {
    const token = localStorage.getItem('token');
    const postData = {
      stock_id: stockId,
      birthAlert,
      valueAlert: valueAlert !== '' ? parseFloat(valueAlert) : null,
      valueAlertEnabled,
    };

    fetch('/api/watch_list', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(postData),
    })
      .then((response) => response.json())
      .then((data) => console.log('Watch list updated:', data))
      .catch((error) => console.error('Error updating watch list:', error));
  };

  // Toggle birth alert
  const handleToggleBirthAlert = (stockId) => {
    setStocksData((prevData) =>
      prevData.map((stock) =>
        stock.stock_id === stockId
          ? { ...stock, birthAlert: !stock.birthAlert }
          : stock
      )
    );

    const updatedStock = stocksData.find((stock) => stock.stock_id === stockId);
    if (updatedStock) {
      postWatchListUpdate(stockId, !updatedStock.birthAlert, updatedStock.valueAlert, updatedStock.valueAlertEnabled);
    }
  };

  // Handle value alert change
  const handleValueAlertChange = (stockId, value) => {
    setStocksData((prevData) =>
      prevData.map((stock) =>
        stock.stock_id === stockId ? { ...stock, valueAlert: value } : stock
      )
    );
  };

  // Toggle value alert enabled
  const handleToggleValueAlert = (stockId) => {
    setStocksData((prevData) =>
      prevData.map((stock) =>
        stock.stock_id === stockId
          ? { ...stock, valueAlertEnabled: !stock.valueAlertEnabled }
          : stock
      )
    );

    const updatedStock = stocksData.find((stock) => stock.stock_id === stockId);
    if (updatedStock) {
      postWatchListUpdate(stockId, updatedStock.birthAlert, updatedStock.valueAlert, !updatedStock.valueAlertEnabled);
    }
  };

  return (
    <div className="watch-list-page">
      <div className="filter-container">
        <label htmlFor="category-filter">Select a Category:</label>
        <select id="category-filter" value={selectedCategory} onChange={handleCategoryChange}>
          <option value="">-- Select a Category --</option>
          {categories.map((category, index) => (
            <option key={index} value={category}>
              {category.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
      </div>

      {stocksData.length > 0 && (
        <table className="stocks-table">
          <thead>
            <tr>
              <th>Stock Name</th>
              <th>Birth Alert</th>
              <th>Price Exceeds Alert</th>
            </tr>
          </thead>
          <tbody>
            {stocksData.map((stock) => (
              <tr key={stock.stock_id}>
                <td>{stock.name}</td>
                <td>
                  <label className="switch">
                    <input
                      type="checkbox"
                      checked={stock.birthAlert || false}
                      onChange={() => handleToggleBirthAlert(stock.stock_id)}
                    />
                    <span className="slider round"></span>
                  </label>
                </td>
                <td>
                  <div className="value-alert-container">
                    <input
                      type="number"
                      value={stock.valueAlert || ''}
                      onChange={(e) => handleValueAlertChange(stock.stock_id, e.target.value)}
                      min="1"
                      max="1000"
                    />
                    <button onClick={() => handleToggleValueAlert(stock.stock_id)}>
                      {stock.valueAlertEnabled ? 'Unset' : 'Set'}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default WatchList;

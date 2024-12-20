import React, { useEffect, useState } from 'react';
import StockGraphPopup from './StockGraphPopup';
import './AllStocksView.css';
import apiFetch from './api';

const AllStocksView = () => {
  const [stocksData, setStocksData] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState('All'); // Default to showing all categories
  const [selectedStock, setSelectedStock] = useState(null);
  const [stockHistory, setStockHistory] = useState([]);
  
  useEffect(() => {
    apiFetch('/api/stocks_data')
      .then((response) => response.json())
      .then((data) => {
        console.log("Fetched data: ", data);
        setStocksData(data);
      })
      .catch((error) => console.error('Error fetching stocks data:', error));
  }, []);

  const fetchStockHistory = (stockId, stockName) => {
    console.log("Fetching history for stock ID: ", stockId);
    apiFetch(`/api/stock_history/${stockId}`)
      .then((response) => response.json())
      .then((data) => {
        console.log("Fetched stock history: ", data);
        setStockHistory(data);
        setSelectedStock({ id: stockId, name: stockName });
      })
      .catch((error) => console.error('Error fetching stock history:', error));
  };

  const handleCategoryChange = (event) => {
    setSelectedCategory(event.target.value);
  };

  if (!stocksData) {
    return <div>Loading...</div>;
  }

  const renderStocksTable = () => {
    let categories = stocksData.topCategories.concat(stocksData.bottomCategories);
    let stockSlices = stocksData.topStockSlices.concat(stocksData.bottomStockSlices);

    if (selectedCategory !== 'All') {
      const categoryIndex = categories.indexOf(selectedCategory);
      categories = categoryIndex !== -1 ? [categories[categoryIndex]] : [];
      stockSlices = categoryIndex !== -1 ? [stockSlices[categoryIndex]] : [];
    }

    // Group categories into rows of three
    const groupedCategories = [];
    for (let i = 0; i < categories.length; i += 3) {
      groupedCategories.push({
        categories: categories.slice(i, i + 3),
        slices: stockSlices.slice(i, i + 3),
      });
    }

    return groupedCategories.map((group, groupIndex) => (
      <div key={groupIndex} className="category-row">
        {group.categories.map((category, categoryIndex) => (
          <table key={category} className="stocks-table">
            <thead>
              <tr>
                <th colSpan="2" className="category-title">
                  {category.replace(/_/g, ' ')}
                </th>
              </tr>
              <tr>
                <th className="label">Stock</th>
                <th className="label">Price</th>
              </tr>
            </thead>
            <tbody>
              {group.slices[categoryIndex].map((stock, rowIndex) => {
                const isUnavailable = stock.price === 0;

                return (
                  <tr key={rowIndex}>
                    <td
                      className={`stock ${isUnavailable ? 'unavailable' : ''} clickable`}
                      onClick={() => fetchStockHistory(stock.stock_id, stock.name)}
                    >
                      {stock.name}
                    </td>
                    <td className={`price ${isUnavailable ? 'unavailable' : ''}`}>
                      £{stock.price.toFixed(1)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ))}
      </div>
    ));
  };

  return (
    <div className="all-stocks-view">
      <div className="filter-container">
        <label htmlFor="category-filter">Filter by Category:</label>
        <select id="category-filter" value={selectedCategory} onChange={handleCategoryChange}>
          <option value="All">All</option>
          {stocksData.topCategories.concat(stocksData.bottomCategories).map((category, index) => (
            <option key={index} value={category}>
              {category.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
      </div>
      {renderStocksTable()}
      {selectedStock && (
        <StockGraphPopup
          stockName={selectedStock.name}
          data={stockHistory}
          onClose={() => setSelectedStock(null)}
        />
      )}
    </div>
  );
};

export default AllStocksView;

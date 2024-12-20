import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import StockGraphPopup from './StockGraphPopup';
import './CategoryPage.css';
import apiFetch from './api';

const CategoryPage = () => {
  const { categoryId } = useParams();
  const [stocks, setStocks] = useState([]);
  const [playerPortfolio, setPlayerPortfolio] = useState({});
  const [transactionAmounts, setTransactionAmounts] = useState({});
  const [selectedStock, setSelectedStock] = useState(null);
  const [stockHistory, setStockHistory] = useState([]);
  const [totalStocksOwned, setTotalStocksOwned] = useState(0); // Track total stocks owned

  const fetchStockHistory = (stockId, stockName) => {
    const token = localStorage.getItem('token');
    apiFetch(`/api/stock_history/${stockId}`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    })
      .then((response) => response.json())
      .then((data) => {
        setStockHistory(data);
        setSelectedStock({ id: stockId, name: stockName });
      })
      .catch((error) => console.error('Error fetching stock history:', error));
  };

  useEffect(() => {
    const token = localStorage.getItem('token');

    apiFetch(`/api/stocks/${categoryId}`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    })
      .then((response) => response.json())
      .then((data) => {
        setStocks(data);
        const initialTransactionAmounts = {};
        data.forEach((stock) => {
          initialTransactionAmounts[stock.stock_id] = 0;
        });
        setTransactionAmounts(initialTransactionAmounts);
      })
      .catch((error) => console.error('Error fetching stocks:', error));

    apiFetch('/api/player_portfolio', {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    })
      .then((response) => response.json())
      .then((data) => {
        const portfolio = {};
        let totalStocks = 0;
        data.forEach((item) => {
          portfolio[item.stock_id] = item;
          totalStocks += item.owned;
        });
        setPlayerPortfolio(portfolio);
        setTotalStocksOwned(totalStocks);
      })
      .catch((error) => console.error('Error fetching player portfolio:', error));
  }, [categoryId]);

  const handleBuySell = (stockId) => {
    const change = transactionAmounts[stockId];
    if (change === 0) return;

    const token = localStorage.getItem('token');

    apiFetch('/api/update_portfolio', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ [stockId]: change }),
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.status === 'success') {
          apiFetch('/api/player_portfolio', {
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
          })
            .then((response) => response.json())
            .then((data) => {
              const portfolio = {};
              let totalStocks = 0;
              data.forEach((item) => {
                portfolio[item.stock_id] = item;
                totalStocks += item.owned;
              });
              setPlayerPortfolio(portfolio);
              setTotalStocksOwned(totalStocks);
              setTransactionAmounts((prevAmounts) => ({ ...prevAmounts, [stockId]: 0 }));
            })
            .catch((error) => console.error('Error fetching player portfolio:', error));
        } else {
          console.error('Transaction failed:', data.message);
        }
      })
      .catch((error) => console.error('Error updating portfolio:', error));
  };

  const handleTransactionChange = (stockId, delta) => {
    const ownedItem = playerPortfolio[stockId] || { owned: 0 };
    const newAmount = transactionAmounts[stockId] + delta;

    // Rule 1: Stop increasing if the total will exceed 75
    if (ownedItem.owned + newAmount > 75) {
      return;
    }

    // Rule 2: Do not allow holding more than 600 stocks in total
    if (totalStocksOwned + delta > 600 && delta > 0) {
      return;
    }

    setTransactionAmounts((prevAmounts) => ({
      ...prevAmounts,
      [stockId]: newAmount,
    }));
  };

  return (
    <div className="category-page">
  <h2>{categoryId.replace('_', ' ')}</h2>
  <div className="stock-table-container">
    <table className="stock-table">
      <thead>
        <tr>
          <th>Stock Name</th>
          <th>Price</th>
          <th>Owned</th>
          <th>Changes</th>
          <th>Purchase Price</th>
          <th>Predicted Profit</th>
        </tr>
      </thead>
      <tbody>
        {stocks.map((stock) => {
          const ownedItem = playerPortfolio[stock.stock_id] || { owned: 0, purchase_price: 0 };
          const change = transactionAmounts[stock.stock_id] || 0;
          const purchasePrice = ownedItem.purchase_price || 0;
          const ownedQuantity = ownedItem.owned || 0;
          const currentProfit = ownedQuantity > 0 ? (stock.price - purchasePrice) * ownedQuantity : 0;
          const profitClass = currentProfit > 0 ? 'positive-profit' : currentProfit < 0 ? 'negative-profit' : '';
          const rowClass = stock.price > 0 ? (ownedQuantity > 0 ? 'owned' : '') : 'unavailable';

          const canBuyMore = ownedQuantity + change < 75 && totalStocksOwned + change < 600;
          const hasPreviouslyOwned = ownedItem.owned > 0 || ownedItem.purchase_price > 0;

          return (
            <tr key={stock.stock_id} className={rowClass}>
              <td className="clickable" onClick={() => apiFetchStockHistory(stock.stock_id, stock.name)}>
                {stock.name}
              </td>
              <td>{stock.price > 0 ? `£${stock.price}` : 'N/A'}</td>
              <td>{ownedQuantity}</td>
              <td>
                <div className="change-buttons">
                  <button onClick={() => handleTransactionChange(stock.stock_id, -10)} disabled={ownedQuantity + change < 10}>
                    --
                  </button>
                  <button onClick={() => handleTransactionChange(stock.stock_id, -1)} disabled={ownedQuantity + change <= 0}>
                    -
                  </button>
                  <span>{change}</span>
                  <button onClick={() => handleTransactionChange(stock.stock_id, 1)} disabled={!canBuyMore || stock.price <= 0 || hasPreviouslyOwned}>
                    +
                  </button>
                  <button onClick={() => handleTransactionChange(stock.stock_id, 10)} disabled={!canBuyMore || stock.price <= 0 || hasPreviouslyOwned}>
                    ++
                  </button>
                  <button onClick={() => handleBuySell(stock.stock_id)} disabled={change === 0}>
                    {change < 0 ? 'Sell' : 'Buy'}
                  </button>
                </div>
              </td>
              <td>{purchasePrice > 0 ? `£${purchasePrice}` : 'N/A'}</td>
              <td className={profitClass}>£{currentProfit.toFixed(2)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  </div>
  {selectedStock && (
    <StockGraphPopup stockName={selectedStock.name} data={stockHistory} onClose={() => setSelectedStock(null)} />
  )}
</div>

  );
};

export default CategoryPage;

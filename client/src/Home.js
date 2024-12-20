import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import StockGraphPopup from './StockGraphPopup';
import './Home.css';
import apiFetch from './api';

const Home = () => {
  const [portfolio, setPortfolio] = useState([]);
  const [selectedStock, setSelectedStock] = useState(null);
  const [stockHistory, setStockHistory] = useState([]);
  const [completedSales, setCompletedSales] = useState([]);
  const [showPortfolio, setShowPortfolio] = useState(true); // Toggle state for portfolio visibility
  const [showCompletedSales, setShowCompletedSales] = useState(true); // Toggle state for sales visibility
  const navigate = useNavigate();

  useEffect(() => {
    fetchPortfolio();
    fetchCompletedSales();

    const interval = setInterval(() => {
      fetchPortfolio();
      fetchCompletedSales();
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  const fetchPortfolio = () => {
    const token = localStorage.getItem('token');
    apiFetch('/api/player_portfolio', {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    })
      .then((response) => response.json())
      .then((data) => setPortfolio(Array.isArray(data) ? data : []))
      .catch((error) => console.error('Error fetching portfolio:', error));
  };

  const fetchCompletedSales = () => {
    const token = localStorage.getItem('token');
    apiFetch('/api/player_info', {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    })
      .then((response) => response.json())
      .then((data) => setCompletedSales(data.completed_sales || []))
      .catch((error) => console.error('Error fetching completed sales:', error));
  };

  const fetchStockHistory = (stockId, stockName) => {
    const token = localStorage.getItem('token');
    apiFetch(`/api/stock_history/${stockId}`, {
      headers: {
        Authorization: `Bearer ${token}`,
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

  const calculateProfit = (currentValue, purchasePrice, quantity) => {
    return currentValue - purchasePrice * quantity;
  };

  const sellAllStocks = (stockId, quantity) => {
    const token = localStorage.getItem("token");
    apiFetch("/api/update_portfolio", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ [stockId]: -quantity }), // Negative value indicates selling
    })
      .then(() => {
        fetchPortfolio(); // Refresh the portfolio after selling
      })
      .catch((error) => console.error("Error selling stocks:", error));
  };

  return (
    <div className="home-container">
      <h1 className="home-title">Welcome to the Jewish Stock Exchange</h1>

      <div className="navigation-buttons">
        <Link to="/search" className="nav-button">
          Buy Stocks
        </Link>
        <Link to="/sell-stocks" className="nav-button">
          Sell Stocks
        </Link>
        <Link to="/all-stocks" className="nav-button">
          All Stocks Data Feed
        </Link>
        <Link to="/watch-list" className="nav-button">
          Watch List
        </Link>
        <Link to="/historical-events" className="nav-button">
          Historical Events Feed
        </Link>
      </div>

       <div className="portfolio-section">
        <div className="section-header">
          <h2>My Portfolio</h2>
          <button
            className="toggle-button"
            onClick={() => setShowPortfolio((prev) => !prev)}
          >
            {showPortfolio ? 'Hide' : 'Show'}
          </button>
        </div>
        {showPortfolio && (
  <table className="portfolio-table">
    <thead>
      <tr>
        <th>Stock Name</th>
        <th>Category</th>
        <th>Quantity</th>
        <th>Current Value</th>
        <th>Potential Profit</th>
      </tr>
    </thead>
    <tbody>
      {[...portfolio]
        .sort((a, b) => {
          const profitA = calculateProfit(a.current_value, a.purchase_price, a.owned);
          const profitB = calculateProfit(b.current_value, b.purchase_price, b.owned);
          return profitB - profitA; // Sort in decreasing order of profit
        })
        .map((item) => {
          const currentProfit = calculateProfit(item.current_value, item.purchase_price, item.owned);
          const profitClass =
            currentProfit > 0 ? 'positive-profit' : currentProfit < 0 ? 'negative-profit' : '';
          return (
            <tr key={item.stock_id}>
              <td
                className="clickable"
                onClick={() => fetchStockHistory(item.stock_id, item.name)}
              >
                {item.name}
              </td>
              <td>{item.category}</td>
              <td>{item.owned}</td>
              <td>£{Math.round(item.current_value)}</td>
              <td className={`potential-profit-cell ${profitClass}`}>£{Math.round(currentProfit)}
              <button
                        className="sell-all-button"
                        onClick={() => sellAllStocks(item.stock_id, item.owned)}
                      >
                        Sell All
                      </button>
              </td>
            </tr>
          );
        })}
    </tbody>
  </table>
)}

      </div>

      <div className="completed-sales-section">
        <div className="section-header">
          <h2>Completed Sales</h2>
          <button
            className="toggle-button"
            onClick={() => setShowCompletedSales((prev) => !prev)}
          >
            {showCompletedSales ? 'Hide' : 'Show'}
          </button>
        </div>
        {showCompletedSales && (
          <table className="sales-table">
            <thead>
            <tr>
              <th>Stock Name</th>
              <th>Price Purchased</th>
              <th>Number of Stocks Sold</th>
              <th>Price Sold</th>
              <th>Profit</th>
            </tr>
          </thead>
          <tbody>
            {completedSales.map((sale, index) => {
              const profitClass =
                sale.profit > 0 ? 'positive-profit' : sale.profit < 0 ? 'negative-profit' : '';
              return (
                <tr key={index}>
                  <td>{sale.stock_name}</td>
                  <td>£{Math.round(sale.price_purchased)}</td>
                  <td>{sale.quantity_sold}</td>
                  <td>£{Math.round(sale.price_sold)}</td>
                  <td className={profitClass}>
                    £{Math.round(sale.profit)} ({Math.round(sale.percentage_return)}%)
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        )}
      </div>

      {selectedStock && (
        <StockGraphPopup
          stockName={selectedStock.name}
          data={stockHistory}
          onClose={() => setSelectedStock(null)}
        />
      )}
      <div className="footer">Copyright Dan Simons 2024</div>
    </div>
  );
};

export default Home;

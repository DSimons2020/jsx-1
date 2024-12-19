import React, { useState, useEffect } from "react";
import StockGraphPopup from "./StockGraphPopup";
import "./SellStocks.css";

const SellStocksPage = () => {
  const [stocks, setStocks] = useState([]); // Original owned stocks
  const [sortedStocks, setSortedStocks] = useState([]); // Sorted stocks
  const [playerPortfolio, setPlayerPortfolio] = useState({});
  const [transactionAmounts, setTransactionAmounts] = useState({});
  const [selectedStock, setSelectedStock] = useState(null);
  const [stockHistory, setStockHistory] = useState([]);
  const [sortOption, setSortOption] = useState("profit-desc"); // Default sorting by profit

  useEffect(() => {
    const fetchInitialData = async () => {
      const token = localStorage.getItem("token");
      try {
        // Fetch player portfolio
        const portfolioResponse = await fetch("/api/player_portfolio", {
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        });
        const portfolioData = await portfolioResponse.json();
        const portfolio = {};
        portfolioData.forEach((item) => {
          portfolio[item.stock_id] = item;
        });
        setPlayerPortfolio(portfolio);

        // Fetch stocks
        const response = await fetch("/api/stocks_data", {
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        });
        const data = await response.json();
        const allStocks = data.topStockSlices.concat(data.bottomStockSlices).flat();

        // Filter stocks owned by the player
        const ownedStocks = allStocks.filter(
          (stock) => portfolio[stock.stock_id]?.owned > 0
        );
        setStocks(ownedStocks);
      } catch (error) {
        console.error("Error fetching initial data:", error);
      }
    };

    fetchInitialData();
  }, []); // Run only once

  useEffect(() => {
    const sortStocks = () => {
      let sorted = [...stocks];
      switch (sortOption) {
        case "profit-desc":
          sorted.sort((a, b) => {
            const profitA =
              (a.price - (playerPortfolio[a.stock_id]?.purchase_price || 0)) *
              (playerPortfolio[a.stock_id]?.owned || 0);
            const profitB =
              (b.price - (playerPortfolio[b.stock_id]?.purchase_price || 0)) *
              (playerPortfolio[b.stock_id]?.owned || 0);
            return profitB - profitA;
          });
          break;
        case "price-desc":
          sorted.sort((a, b) => b.price - a.price);
          break;
        case "name-asc":
          sorted.sort((a, b) => a.name.localeCompare(b.name));
          break;
        case "name-desc":
          sorted.sort((a, b) => b.name.localeCompare(a.name));
          break;
        default:
          break;
      }
      setSortedStocks(sorted);
    };

    sortStocks();
  }, [stocks, sortOption, playerPortfolio]); // Trigger sorting only when relevant data changes

  const fetchStockHistory = (stockId, stockName) => {
    fetch(`/api/stock_history/${stockId}`)
      .then((response) => response.json())
      .then((data) => {
        setStockHistory(data);
        setSelectedStock({ id: stockId, name: stockName });
      })
      .catch((error) => console.error("Error fetching stock history:", error));
  };

  const handleTransactionChange = (stockId, delta) => {
    const ownedItem = playerPortfolio[stockId] || { owned: 0 };
    const newAmount = (transactionAmounts[stockId] || 0) + delta;

    // Prevent invalid sell operations
    if (ownedItem.owned + newAmount < 0) {
      return;
    }

    setTransactionAmounts((prev) => ({
      ...prev,
      [stockId]: newAmount,
    }));
  };

  const handleSell = (stockId) => {
    const change = transactionAmounts[stockId];
    if (change === 0) return;

    const token = localStorage.getItem("token");
    fetch("/api/update_portfolio", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ [stockId]: change }),
    })
      .then(() => {
        const updatedPortfolio = { ...playerPortfolio };
        updatedPortfolio[stockId].owned += change;
        if (updatedPortfolio[stockId].owned === 0) {
          delete updatedPortfolio[stockId];
        }
        setPlayerPortfolio(updatedPortfolio);

        // Update filtered stocks
        setStocks((prevStocks) =>
          prevStocks.filter((stock) => updatedPortfolio[stock.stock_id]?.owned > 0)
        );

        setTransactionAmounts((prev) => ({ ...prev, [stockId]: 0 }));
      })
      .catch((error) => console.error("Error updating portfolio:", error));
  };

  return (
    <div className="sell-stocks-page">
      <h2>Sell Stocks</h2>

      <div className="sort-dropdown">
        <label htmlFor="sort-options">View by:</label>
        <select
          id="sort-options"
          value={sortOption}
          onChange={(e) => setSortOption(e.target.value)}
        >
          <option value="profit-desc">Sort Profit (largest to smallest)</option>
          <option value="price-desc">Sort Price (highest to lowest)</option>
          <option value="name-asc">Sort Alphabetically (A-Z)</option>
          <option value="name-desc">Sort Alphabetically (Z-A)</option>
        </select>
      </div>

      <div className="stock-table-container">
        <table className="stock-table">
          <thead>
            <tr>
              <th>Stock Name</th>
              <th>Price</th>
              <th>Category</th>
              <th>Owned</th>
              <th>Sell</th>
              <th>Purchase Price</th>
              <th>Predicted Profit</th>
            </tr>
          </thead>
          <tbody>
            {sortedStocks.map((stock) => {
              const ownedItem = playerPortfolio[stock.stock_id] || { owned: 0, purchase_price: 0 };
              const change = transactionAmounts[stock.stock_id] || 0;
              const purchasePrice = ownedItem.purchase_price || 0;
              const ownedQuantity = ownedItem.owned || 0;
              const currentProfit =
                ownedQuantity > 0 ? (stock.price - purchasePrice) * ownedQuantity : 0;
              const profitClass =
                currentProfit > 0 ? "positive-profit" : currentProfit < 0 ? "negative-profit" : "";

              return (
                <tr key={stock.stock_id}>
                  <td
                    className="clickable"
                    onClick={() => fetchStockHistory(stock.stock_id, stock.name)}
                  >
                    {stock.name}
                  </td>
                  <td>£{stock.price.toFixed(1)}</td>
                  <td>{stock.category || "N/A"}</td>
                  <td>{ownedQuantity}</td>
                  <td>
                    <div className="change-buttons">
                      <button
                        onClick={() => handleTransactionChange(stock.stock_id, -10)}
                        disabled={ownedQuantity + change < 10}
                      >
                        --10
                      </button>
                      <button
                        onClick={() => handleTransactionChange(stock.stock_id, -1)}
                        disabled={ownedQuantity + change <= 0}
                      >
                        -1
                      </button>
                      <span>{change}</span>
                      <button
                        onClick={() => handleTransactionChange(stock.stock_id, 1)}
                        disabled={change >= ownedQuantity}
                      >
                        +1
                      </button>
                      <button onClick={() => handleSell(stock.stock_id)} disabled={change === 0}>
                        Sell
                      </button>
                    </div>
                  </td>
                  <td>£{purchasePrice.toFixed(1)}</td>
                  <td className={profitClass}>£{currentProfit.toFixed(2)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
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

export default SellStocksPage;

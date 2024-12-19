import React, { useState, useEffect } from "react";
import StockGraphPopup from "./StockGraphPopup";
import "./SearchPage.css";

const SearchPage = () => {
  const [stocks, setStocks] = useState([]);
  const [categories, setCategories] = useState([]);
  const [filteredStocks, setFilteredStocks] = useState([]);
  const [playerPortfolio, setPlayerPortfolio] = useState({});
  const [transactionAmounts, setTransactionAmounts] = useState({});
  const [selectedStock, setSelectedStock] = useState(null);
  const [stockHistory, setStockHistory] = useState([]);
  const [filterOptions, setFilterOptions] = useState({
    owned: null,
    categories: ["All"],
    name: "",
    priceRange: [7, 100],
    bornStatus: ["Born"],
  });
  const [sortOption, setSortOption] = useState("name-asc"); // Default sort option
  const [showFilters, setShowFilters] = useState(false); // Controls visibility of filter menu
  const [playerBalance, setPlayerBalance] = useState(0); // Add this line

  

  useEffect(() => {
    const fetchInitialData = async () => {
      const token = localStorage.getItem("token");

      try {
        // Fetch stocks and categories
        const response = await fetch("/api/stocks_data", {
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        });
        const data = await response.json();
        const allStocks = data.topStockSlices
          .concat(data.bottomStockSlices)
          .flat()
          .sort((a, b) => a.name.localeCompare(b.name)); // Default sort: A-Z
        setStocks(allStocks);
        // Apply default filter for "Born" stocks
      const initialFilteredStocks = allStocks.filter((stock) => stock.price > 0); // Filter "Born" stocks
      setFilteredStocks(initialFilteredStocks);

        const combinedCategories = data.topCategories.concat(data.bottomCategories);
        setCategories(["All", ...combinedCategories]);
      } catch (error) {
        console.error("Error fetching stocks data:", error);
      }

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
      } catch (error) {
        console.error("Error fetching player portfolio:", error);
      }
      // Fetch player balance (assuming an API endpoint provides this)
      const playerInfoResponse = await fetch("/api/player_info", {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });
      const playerInfo = await playerInfoResponse.json();
      setPlayerBalance(playerInfo.balance); // Store balance in state
    } 
    fetchInitialData();
  }, []);

  const handleSearch = () => {
    const { owned, categories, name, priceRange, bornStatus } = filterOptions;

    let filtered = [...stocks];

    // Apply filters
    if (owned === "yes") {
      filtered = filtered.filter((stock) => playerPortfolio[stock.stock_id]?.owned > 0);
    } else if (owned === "no") {
      filtered = filtered.filter((stock) => !(playerPortfolio[stock.stock_id]?.owned > 0));
    }

    if (categories.length > 0 && !categories.includes("All")) {
      filtered = filtered.filter((stock) => categories.includes(stock.category));
    }

    if (name) {
      const lowerCaseName = name.toLowerCase();
      filtered = filtered.filter((stock) => stock.name.toLowerCase().includes(lowerCaseName));
    }

    filtered = filtered.filter((stock) => stock.price >= priceRange[0] && stock.price <= priceRange[1]);

    if (bornStatus.length === 1) {
      const isBorn = bornStatus[0] === "Born";
      filtered = filtered.filter((stock) => (stock.price > 0) === isBorn);
    }

    sortStocks(sortOption, filtered);
  };

  const sortStocks = (option, stocksToSort) => {
    let sortedStocks = [...stocksToSort];
    switch (option) {
      case "name-asc":
        sortedStocks.sort((a, b) => a.name.localeCompare(b.name));
        break;
      case "name-desc":
        sortedStocks.sort((a, b) => b.name.localeCompare(a.name));
        break;
      case "price-asc":
        sortedStocks.sort((a, b) => a.price - b.price);
        break;
      case "price-desc":
        sortedStocks.sort((a, b) => b.price - a.price);
        break;
      case "category":
        sortedStocks.sort((a, b) => (a.category || "").localeCompare(b.category || ""));
        break;
      case "owned-desc":
        sortedStocks.sort((a, b) => (playerPortfolio[b.stock_id]?.owned || 0) - (playerPortfolio[a.stock_id]?.owned || 0));
        break;
      default:
        break;
    }
    setFilteredStocks(sortedStocks);
  };

  const fetchStockHistory = (stockId, stockName) => {
    console.log("Fetching history for stock ID: ", stockId);
    fetch(`/api/stock_history/${stockId}`)
      .then((response) => response.json())
      .then((data) => {
        console.log("Fetched stock history: ", data);
        setStockHistory(data);
        setSelectedStock({ id: stockId, name: stockName });
      })
      .catch((error) => console.error("Error fetching stock history:", error));
  };

  const handleSortChange = (option) => {
    setSortOption(option);
    sortStocks(option, filteredStocks);
  };

  const handleTransactionChange = (stockId, delta) => {
    const ownedItem = playerPortfolio[stockId] || { owned: 0 };
    const newAmount = (transactionAmounts[stockId] || 0) + delta;
  
    // Get the stock's price
    const stock = stocks.find((s) => s.stock_id === stockId);
    const stockPrice = stock ? stock.price : 0;
  
    // Check available balance
  const totalCost = stockPrice * newAmount;
  
    // Prevent reducing below 0 or exceeding available balance
  if (
    ownedItem.owned + newAmount < 0 || // Cannot sell more than owned
    (newAmount > 0 && totalCost > playerBalance) || // Cannot exceed balance
    ownedItem.owned + newAmount > 75 // Optional: Cap at 75 stocks
  ) {
    return; // Prevent invalid updates
  }
  
    setTransactionAmounts((prev) => ({
      ...prev,
      [stockId]: newAmount,
    }));
  };
  
  
  const handleBuySell = (stockId) => {
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
        if (!updatedPortfolio[stockId]) {
          updatedPortfolio[stockId] = { owned: 0, purchase_price: 0 };
        }
        updatedPortfolio[stockId].owned += change;
        setPlayerPortfolio(updatedPortfolio);
        setTransactionAmounts((prev) => ({ ...prev, [stockId]: 0 }));
      })
      .catch((error) => console.error("Error updating portfolio:", error));
  };

  return (
    <div className="search-page">
      <h2>Search Stocks</h2>
      <div className="filter-controls">
        <button className="filter-button" onClick={() => setShowFilters((prev) => !prev)}>
          {showFilters ? "Hide Filters" : "Show Filters"}
        </button>
        <div className="sort-dropdown">
          <label htmlFor="sort-options">View by:</label>
          <select
            id="sort-options"
            value={sortOption}
            onChange={(e) => handleSortChange(e.target.value)}
          >
            <option value="name-asc">Alphabetical (A-Z)</option>
            <option value="name-desc">Alphabetical (Z-A)</option>
            <option value="price-asc">Price (Low to High)</option>
            <option value="price-desc">Price (High to Low)</option>
            <option value="category">Category (Alphabetical)</option>
            <option value="owned-desc">Owned (Most to Least)</option>
          </select>
        </div>
      </div>
      {showFilters && (
        <div className="filter-menu">
          {/* Filters */}
          <label>
            Owned:
            <select
              value={filterOptions.owned || ""}
              onChange={(e) =>
                setFilterOptions({ ...filterOptions, owned: e.target.value || null })
              }
            >
              <option value="">Any</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </label>
          <label>
            Categories:
            <select
              multiple
              value={filterOptions.categories}
              onChange={(e) =>
                setFilterOptions({
                  ...filterOptions,
                  categories: Array.from(e.target.selectedOptions, (o) => o.value),
                })
              }
            >
              {categories.map((category, index) => (
                <option key={index} value={category}>
                  {category.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </label>
          <label>
            Name:
            <input
              type="text"
              value={filterOptions.name}
              onChange={(e) => setFilterOptions({ ...filterOptions, name: e.target.value })}
            />
          </label>
          <label>
  Price Range:
  <div className="dual-slider-container">
    <input
      type="range"
      min="0"
      max="100"
      value={filterOptions.priceRange[0]}
      onChange={(e) => {
        const min = Math.min(Number(e.target.value), filterOptions.priceRange[1] - 1);
        setFilterOptions((prev) => ({ ...prev, priceRange: [min, prev.priceRange[1]] }));
      }}
      className="range-input range-min"
    />
    <input
      type="range"
      min="0"
      max="100"
      value={filterOptions.priceRange[1]}
      onChange={(e) => {
        const max = Math.max(Number(e.target.value), filterOptions.priceRange[0] + 1);
        setFilterOptions((prev) => ({ ...prev, priceRange: [prev.priceRange[0], max] }));
      }}
      className="range-input range-max"
    />
    <div
      className="range-track"
      style={{
        left: `${(filterOptions.priceRange[0] / 100) * 100}%`,
        right: `${100 - (filterOptions.priceRange[1] / 100) * 100}%`,
      }}
    ></div>
  </div>
  {`£${filterOptions.priceRange[0]} - £${filterOptions.priceRange[1]}`}
</label>
          <label>
            Born Status:
            <select
              multiple
              value={filterOptions.bornStatus}
              onChange={(e) =>
                setFilterOptions({
                  ...filterOptions,
                  bornStatus: Array.from(e.target.selectedOptions, (o) => o.value),
                })
              }
            >
              <option value="Born">Born</option>
              <option value="Yet to be born">Yet to be born</option>
            </select>
          </label>
          <button onClick={handleSearch}>Apply Filters</button>
        </div>
      )}
      <div className="stock-table-container">
        <table className="stock-table">
          <thead>
            <tr>
              <th>Stock Name</th>
              <th>Price</th>
              <th>Category</th>
              <th>Owned</th>
              <th>Changes</th>
              <th>Purchase Price</th>
              <th>Predicted Profit</th>
            </tr>
          </thead>
          <tbody>
            {filteredStocks.map((stock) => {
              const ownedItem = playerPortfolio[stock.stock_id] || { owned: 0, purchase_price: 0 };
              const change = transactionAmounts[stock.stock_id] || 0;
              const purchasePrice = ownedItem.purchase_price || 0;
              const ownedQuantity = ownedItem.owned || 0;
              const currentProfit =
                ownedQuantity > 0 ? (stock.price - purchasePrice) * ownedQuantity : 0;
              const profitClass =
                currentProfit > 0 ? "positive-profit" : currentProfit < 0 ? "negative-profit" : "";
              const rowClass = stock.price > 0 ? (ownedQuantity > 0 ? "owned" : "") : "unavailable";

              return (
                <tr key={stock.stock_id} className={rowClass}>
                   <td
                  className="clickable"
                  onClick={() => fetchStockHistory(stock.stock_id, stock.name)}
                >{stock.name}</td>
                  <td>£{stock.price.toFixed(1)}</td>
                  <td>{stock.category || "N/A"}</td>
                  <td>{ownedQuantity}</td>
                  <td>
                    <div className="change-buttons">
                      <button
                        onClick={() => handleTransactionChange(stock.stock_id, -10)}
                        disabled={ownedQuantity + change < 10}
                      >
                        --
                      </button>
                      <button
                        onClick={() => handleTransactionChange(stock.stock_id, -1)}
                        disabled={ownedQuantity + change <= 0}
                      >
                        -
                      </button>
                      <span>{change}</span>
                      <button
                        onClick={() => handleTransactionChange(stock.stock_id, 1)}
                        disabled={stock.price <= 0}
                      >
                        +
                      </button>
                      <button
                        onClick={() => handleTransactionChange(stock.stock_id, 10)}
                        disabled={stock.price <= 0}
                      >
                        ++
                      </button>
                      <button onClick={() => handleBuySell(stock.stock_id)} disabled={change === 0}>
                        {change < 0 ? "Sell" : "Buy"}
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

export default SearchPage;

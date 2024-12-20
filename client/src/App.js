import React, { useEffect, useState } from 'react';
import { BrowserRouter as Router, Route, Routes, Navigate } from 'react-router-dom';
import Home from './Home';
import AllStocksView from './AllStocksView';
import CategoryPage from './CategoryPage';
import Header from './Header';
import Login from './Login';
import HistoricalEventsFeed from './HistoricalEventsFeed';
import Ticker from './Ticker'; // Import the Ticker component
import WatchList from './WatchList';
import SearchPage from './SearchPage';
import SellStocks from './SellStocks';
import apiFetch from './api'; 

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(!!localStorage.getItem('token'));
  const [watchListAlertsEnabled, setWatchListAlertsEnabled] = useState(
    JSON.parse(localStorage.getItem('watchListAlertsEnabled')) || false
  );

  useEffect(() => {
    const verifyAuthentication = async () => {
      try {
        const token = localStorage.getItem('token');
        if (!token) {
          setIsAuthenticated(false);
          return;
        }

        const response = await apiFetch('/api/player_info', {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
        });

        if (response.ok) {
          setIsAuthenticated(true);
        } else {
          setIsAuthenticated(false);
          localStorage.removeItem('token');
          localStorage.removeItem('watchListAlertsEnabled');
          localStorage.removeItem('newsUpdatesEnabled');
          localStorage.removeItem('watchListData');
        }
      } catch (error) {
        setIsAuthenticated(false);
      }
    };

    verifyAuthentication();
  }, []);

  return (
    <Router>
      {isAuthenticated && <Header setWatchListAlertsEnabled={setWatchListAlertsEnabled} watchListAlertsEnabled={watchListAlertsEnabled} />}
      {isAuthenticated && watchListAlertsEnabled && <Ticker />} {/* Conditionally render the Ticker */}
      <Routes>
        <Route path="/" element={isAuthenticated ? <Home /> : <Navigate to="/login" />} />
        <Route path="/login" element={<Login setIsAuthenticated={setIsAuthenticated} />} />
        <Route path="/historical-events" element={isAuthenticated ? <HistoricalEventsFeed /> : <Navigate to="/login" />} />
        <Route path="/category/:categoryId" element={isAuthenticated ? <CategoryPage /> : <Navigate to="/login" />} />
        <Route path="/all-stocks" element={isAuthenticated ? <AllStocksView /> : <Navigate to="/login" />} />
        <Route path="/watch-list" element={isAuthenticated ? <WatchList /> : <Navigate to="/login" />} /> {/* Add WatchList route */}
        <Route path="/search" element={isAuthenticated ? <SearchPage /> : <Navigate to="/login" />} />
        <Route path="/sell-stocks" element={isAuthenticated ? <SellStocks /> : <Navigate to="/login" />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Router>
  );
}

export default App;

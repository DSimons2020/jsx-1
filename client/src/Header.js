import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import './Header.css';

const Header = ({
  currentYear,
  teamName,
  setWatchListAlertsEnabled,
}) => {
  const [playerInfo, setPlayerInfo] = useState({
    balance: 0,
    portfolio_value: 0,
    stocks_owned: 0,
    teamName: '',
  });
  const [gameStatus, setGameStatus] = useState({
    currentYear: 1900,
    gameRunning: false,
  });

  const fetchPlayerInfo = () => {
    const token = localStorage.getItem('token');
    fetch('/api/player_info', {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    })
      .then((response) => response.json())
      .then((data) => {
        setPlayerInfo({
          teamName: data.teamName,
          balance: data.balance,
          portfolio_value: data.portfolio_value,
          stocks_owned: data.stocks_owned,
        });
        setGameStatus({ currentYear: data.current_year, gameRunning: data.game_running });
      })
      .catch((error) => console.error('Error fetching player info:', error));
  };

  useEffect(() => {
    setWatchListAlertsEnabled(true);
    localStorage.setItem('watchListAlertsEnabled', JSON.stringify(true));
    fetchPlayerInfo();
    const intervalId = setInterval(fetchPlayerInfo, 5000);

    return () => clearInterval(intervalId);
  }, [setWatchListAlertsEnabled]);

  return (
    <header className="header">
      <div className="header-container">
        <Link to="/" className="home-link">
          Home
        </Link>
        <div className="center-info">
          <span>Team Name: {playerInfo.teamName || 'Unknown'}</span>
          <span> | Year: {gameStatus.currentYear}</span>
        </div>
        <div className="right-links">
          <ul>
            <li>Portfolio Value: £{playerInfo.portfolio_value.toFixed(2)}</li>
            <li>Cash: £{playerInfo.balance.toFixed(2)}</li>
            <li>Stocks Owned: {playerInfo.stocks_owned}</li>
          </ul>
        </div>
      </div>
    </header>
  );
};

export default Header;

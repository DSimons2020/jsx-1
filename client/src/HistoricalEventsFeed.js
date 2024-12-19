import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './HistoricalEventsFeed.css';

const HistoricalEventsFeed = () => {
  const [events, setEvents] = useState([]);
  const [currentYear, setCurrentYear] = useState(1900);
  const [maxYear, setMaxYear] = useState(1900);
  const [showOwnedOnly, setShowOwnedOnly] = useState(false);
  const [portfolio, setPortfolio] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    fetchCurrentYear();
    fetchPortfolio();
  }, []);

  useEffect(() => {
    fetchEvents(currentYear);
  }, [currentYear, showOwnedOnly]);

  const fetchCurrentYear = async () => {
    const token = localStorage.getItem('token');
    const response = await fetch('/api/game_status', {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });
    const data = await response.json();
    setCurrentYear(data.current_year);
    setMaxYear(data.current_year);
    fetchEvents(data.current_year);
  };

  const fetchPortfolio = async () => {
    const token = localStorage.getItem('token');
    const response = await fetch('/api/player_portfolio', {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });
    const data = await response.json();
    setPortfolio(Array.isArray(data) ? data : []);
  };

  const fetchEvents = async (year) => {
    const token = localStorage.getItem('token');
    const response = await fetch(`/api/historical_events?year=${year}`, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });
    const data = await response.json();

    if (showOwnedOnly) {
      const ownedStockIds = portfolio.map((stock) => stock.stock_id);
      setEvents(data.filter((event) => ownedStockIds.includes(event.stock_id)));
    } else {
      setEvents(data);
    }
  };

  const handleYearChange = (direction) => {
    setCurrentYear((prevYear) => Math.min(maxYear, prevYear + direction));
  };

  const toggleShowOwnedOnly = () => {
    setShowOwnedOnly((prev) => !prev);
  };

  return (
    <div className="historical-events-container">
      <h1>Historical Events Feed</h1>
      <div className="year-navigation">
        <button onClick={() => handleYearChange(-1)} disabled={currentYear <= 1900}>
          Previous
        </button>
        <span className="current-year">{currentYear}</span>
        <button onClick={() => handleYearChange(1)} disabled={currentYear >= maxYear}>
          Next
        </button>
      </div>
      <button className="toggle-owned-only" onClick={toggleShowOwnedOnly}>
        {showOwnedOnly ? 'Show All News' : 'Show My Stocks News'}
      </button>
      <div className="events-feed">
        {events.length > 0 ? (
          events.map((event) => (
            <div key={event.id} className="event-item">
              <h3>
                {event.name} - {event.title}
              </h3>
              <p>{event.detail}</p>
            </div>
          ))
        ) : (
          <p>No events available for this year.</p>
        )}
      </div>
    </div>
  );
};

export default HistoricalEventsFeed;

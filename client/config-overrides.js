const webpack = require('webpack');

module.exports = function override(config) {
  config.resolve.fallback = {
    buffer: require.resolve('buffer/'),
    crypto: require.resolve('crypto-browserify'),
    stream: require.resolve('stream-browserify'),
    vm: require.resolve('vm-browserify'),
    assert: require.resolve('assert/')
  };

  config.plugins.push(
    new webpack.ProvidePlugin({
      Buffer: ['buffer', 'Buffer'],
    })
  );

  return config;
};

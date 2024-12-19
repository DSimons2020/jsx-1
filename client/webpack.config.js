const path = require('path');

module.exports = {
  // Entry point for the application
  entry: './src/index.js', // Adjust this path to your actual entry file

  // Output settings
  output: {
    path: path.resolve(__dirname, 'build'), // Directory to output the build files
    filename: 'main.js', // Name of the output file
  },

  // Resolve settings
  resolve: {
    fallback: {
      crypto: require.resolve('crypto-browserify'),
    },
  },

  // Module settings
  module: {
    rules: [
      {
        test: /\.js$/, // Files to process
        exclude: /node_modules/, // Exclude node_modules
        use: 'babel-loader', // Transpiler for JavaScript files
      },
      {
        test: /\.css$/, // Files to process
        use: ['style-loader', 'css-loader'], // Loaders for CSS files
      },
      // Add other loaders if needed (e.g., for images, fonts, etc.)
    ],
  },

  // Development tools (optional, for easier debugging)
  devtool: 'source-map',

  // Other configuration options
  mode: 'production', // Set to 'development' for development builds
};

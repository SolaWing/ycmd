// Copyright (C) 2011, 2012  Google Inc.
//
// This file is part of YouCompleteMe.
//
// YouCompleteMe is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// YouCompleteMe is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with YouCompleteMe.  If not, see <http://www.gnu.org/licenses/>.

#include "standard.h"
#include "Candidate.h"
#include "Result.h"
#include <cctype>
#include <boost/algorithm/string.hpp>

using boost::algorithm::all;
using boost::algorithm::is_lower;

namespace YouCompleteMe {
  


std::string GetWordBoundaryChars( const std::string &text, std::vector<unsigned short> &indexes) {
  std::string result;

  for ( uint i = 0; i < text.size(); ++i ) {
    bool is_first_char_but_not_punctuation = i == 0 && !ispunct( text[ i ] );
    bool is_good_uppercase = i > 0 &&
                             IsUppercase( text[ i ] ) &&
                             !IsUppercase( text[ i - 1 ] );
    bool is_alpha_after_punctuation = i > 0 &&
                                      ispunct( text[ i - 1 ] ) &&
                                      isalpha( text[ i ] );

    if ( is_first_char_but_not_punctuation ||
         is_good_uppercase ||
         is_alpha_after_punctuation ) {
      result.push_back( tolower( text[ i ] ) );
      indexes.push_back(i);
    }
  }

  return result;
}
  
std::string GetWordBoundaryChars( const std::string &text) {
  std::vector<unsigned short> indexes;
  return GetWordBoundaryChars(text, indexes);
};


Bitset LetterBitsetFromString( const std::string &text ) {
  Bitset letter_bitset;
  foreach ( char letter, text ) {
    letter_bitset.set( IndexForChar( letter ) );
  }

  return letter_bitset;
}

#define kContinueFactor 0.5 //the bigger the factor is, the more score continue match get
#define kMinScore 50        //make result more stable.
  
//the bigger the factor is, the more score word boundary char get
//if more than 1, the word length may be ignored
#define kWBCFactor 0.7
Candidate::Candidate( const std::string &text )
  :
  text_( text ),
  letters_present_( LetterBitsetFromString( text ) )
{
  GetWordBoundaryChars(text, wbc_indexes_);
  wbc_indexes_.push_back(text.size());
  wbc_indexes_.shrink_to_fit();
  
  // calculate total score
  int base_score = text.size() + kMinScore;
  totalScore_ = (base_score + kMinScore + 1) * text.size() / 2;
}


Result Candidate::QueryMatchResult( const std::string &query,
                                    bool case_sensitive ) const {
  double index_sum = 0; // total score

  std::string::const_iterator query_iter = query.begin(), query_end = query.end();
  if ( query_iter == query_end) 
    return Result( true, &text_, totalScore_ - index_sum);

  int index = 0, candidate_len = text_.size();
  
  // score related
  // each char score is base_score * scoreFactor
  // base_score is candidate_len - index
  
  // scoreFactor will increase when match,
  //  and drop to 1 when unmatch
  
  // wbc_index is word boundary index,
  //  if match a word at begin, score will * wordLength
  //  this give word divide query high score.
  double scoreFactor = 1;
  int base_score = candidate_len + kMinScore;
  std::vector<unsigned short>::const_iterator wbc_index = wbc_indexes_.begin();

  if (case_sensitive){
    // only case sensitive when the query char is upper
      
    // When the query letter is uppercase, then we force an uppercase match
    // but when the query letter is lowercase, then it can match both an
    // uppercase and a lowercase letter. This is by design and it's much
    // better than forcing lowercase letter matches.
    char candidate_char, query_char;
    bool query_char_not_upper = false;

    query_char = *query_iter;
    if ( !IsUppercase(query_char) ) query_char_not_upper = true;
    
    while (index < candidate_len){
      candidate_char = text_[index];
      // candi_char convert to lower if query is lower
      if ( query_char_not_upper && IsUppercase(candidate_char) ) 
        candidate_char += kUpperToLowerCount;

      // match
      if ( candidate_char == query_char ){
        // score related
        if (index == *wbc_index){
          // match word begin, get extra score
          int wordLen =*(wbc_index + 1) - *wbc_index;
          index_sum += kMinScore * wordLen * kWBCFactor;
          ++wbc_index;
        }
        index_sum += base_score * scoreFactor;
        // match will increase continueFactor
        scoreFactor += kContinueFactor;
        
        // move to next query char
        ++query_iter;
        // complete, return result
        if ( query_iter == query_end ) 
          return Result( true, &text_,  totalScore_ - index_sum);

        // not complete, reset query char state
        query_char = *query_iter;
        if ( !IsUppercase(query_char) ) query_char_not_upper = true;
        else query_char_not_upper = false;
      
      }else
        // score related
        scoreFactor = 1.0; // drop to 1 when not match
      --base_score;   //base_score reduce when index increase
      //wbc_index must not before index
      if (index == *wbc_index) ++wbc_index;
      
      ++index;
    }
  }else{
    // the notion is similar to above,
    // except this always use lowercase to compare
    char candidate_char, query_char;

    query_char = *query_iter;
    if ( IsUppercase(query_char) ) query_char += kUpperToLowerCount;

    while (index < candidate_len){
      candidate_char = text_[index];
      if ( IsUppercase(candidate_char) ) candidate_char += kUpperToLowerCount;

      if (candidate_char == query_char){
        // score related
        if (index == *wbc_index){
          int wordLen =*(wbc_index + 1) - *wbc_index;
          index_sum += kMinScore * wordLen * kWBCFactor;
          ++wbc_index;
        }
        index_sum += base_score * scoreFactor;
        scoreFactor += kContinueFactor;
        
        ++query_iter;
        if ( query_iter == query_end ) 
          return Result( true, &text_,  totalScore_ - index_sum);

        query_char = *query_iter;
        if ( IsUppercase(query_char) ) query_char += kUpperToLowerCount;
        // score related
      }else
        scoreFactor = 1.0;
      --base_score;
      if (index == *wbc_index) ++wbc_index;
      
      ++index;
    }
  }
  return Result(false);
}

} // namespace YouCompleteMe

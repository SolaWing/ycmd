// Copyright (C) 2011, 2012 Google Inc.
//
// This file is part of ycmd.
//
// ycmd is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// ycmd is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with ycmd.  If not, see <http://www.gnu.org/licenses/>.

#include "standard.h"
#include "Candidate.h"
#include "Result.h"

#include <boost/algorithm/string.hpp>
#include <cctype>
#include <locale>

using boost::algorithm::all;
using boost::algorithm::is_lower;
using boost::algorithm::is_print;

namespace YouCompleteMe {

bool IsPrintable( const std::string &text ) {
  return all( text, is_print( std::locale::classic() ) );
}

std::string GetWordBoundaryChars( const std::string &text, std::vector<unsigned short> &indexes) {
  std::string result;

  // first letter, first upper letter, letter after _ will be consider as a word boundary char
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
    letter_bitset.set( IndexForLetter( letter ) );
  }

  return letter_bitset;
}

#define kContinueFactor 0.25 //the bigger the factor is, the more score continue match get
#define kMinScore 50        //make result more stable.
  
//the bigger the factor is, the more score word boundary char get
//if more than 1, the word length may be ignored
#define kWBCFactor 0.7
#define kEndCharFactor 0.3
Candidate::Candidate( const std::string &text )
  :
  text_( text ),
  letters_present_( LetterBitsetFromString( text ) )
{
  GetWordBoundaryChars(text, wbc_indexes_);
  wbc_indexes_.push_back(text.size());
  wbc_indexes_.shrink_to_fit();
  
  // calculate total score, it's only contain base score
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
  // each char score is base_score
  // base_score is candidate_len - index
  
  // continueCount will increase when match,
  //  and drop to 0 when unmatch
  //  when end or drop to 0, continueCount give bonus score
  
  // wbc_index is word boundary index,
  //  if match a word at begin, score will * wordLength
  //  this give word divide query high score.
  
  // the last char will get extra bonus
  int continueCount = 0;
  int change_case_count = 0;
  int base_score = candidate_len + kMinScore;
  std::vector<unsigned short>::const_iterator wbc_index = wbc_indexes_.begin();

  // if case_sensitive, only case sensitive when the query char is upper
    
  // When the query letter is uppercase, then we force an uppercase match
  // but when the query letter is lowercase, then it can match both an
  // uppercase and a lowercase letter. This is by design and it's much
  // better than forcing lowercase letter matches.
  char candidate_char, query_char;
  bool change_case;
  bool match;

  query_char = *query_iter;
  while (index < candidate_len){
    candidate_char = text_[index];
    match = false;
    change_case = false;
    if (candidate_char == query_char) match = true;
    else{
      if (case_sensitive){
        if (IsLowercase(query_char) && candidate_char + kUpperToLowerCount == query_char){
          change_case = true;
          match = true;
        }
      }
      else if ((IsLowercase(query_char) && candidate_char + kUpperToLowerCount == query_char)
               || (IsUppercase(query_char) && query_char + kUpperToLowerCount == candidate_char)){
        change_case = true;
        match = true;
      }
    }
    // match
#define ContinueScore \
(continueCount * continueCount * base_score * kContinueFactor)
    if ( match ){
      // score related
      if (index == *wbc_index){
        // match word begin, get extra score
        int wordLen =*(wbc_index + 1) - *wbc_index;
        index_sum += kMinScore * wordLen * kWBCFactor;
        ++wbc_index;
      }
      index_sum += base_score;
      if ( change_case ) ++change_case_count;
      // match will increase continueFactor
      ++continueCount;
      
      // move to next query char
      ++query_iter;
      // complete, return result
      if ( query_iter == query_end ) {
        if (continueCount > 1){
          index_sum += ContinueScore;
        }
        // match last char, get extra bonus
        if (index == candidate_len - 1) index_sum += kMinScore * candidate_len * kEndCharFactor;
        return Result( true, &text_,  totalScore_ - index_sum + change_case_count);
      }

      // not complete, reset query char state
      query_char = *query_iter;
    }else {
      if (continueCount > 1){
        index_sum += ContinueScore;
      }
      // score related
      continueCount = 0; // drop to 0 when not match
    }
    
    --base_score;   //base_score reduce when index increase
    //wbc_index must not before index
    if (index == *wbc_index) ++wbc_index;
    
    ++index;
  }
  return Result(false);
}

} // namespace YouCompleteMe
